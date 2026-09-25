"""Cyber Risk Assessment — backend reproduzível para o DATA MASTER.

O servidor utiliza o catálogo local como fonte normativa autoritativa e não
persiste imagens, prompts contendo evidências ou respostas da IA.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from io import BytesIO
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from catalog import ControlCatalog, load_catalog
from demo_mode import DemoRequest, DemoResponse, list_scenarios, get_demo_image, canned_result
from config import ROOT, settings
from inference import GeminiAnalyzer, InvalidModelResponse
from prompts import PROMPT_VERSION
from schemas import AuditRequest, AuditResponse, GeminiAnalysis, TIER

LOGGER = logging.getLogger('cyberrisk')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
Image.MAX_IMAGE_PIXELS = 20_000_000


def decode_image(data_url: str, max_bytes: int) -> tuple[bytes, str]:
    """Valida MIME real, tamanho, dimensões e remove metadados EXIF da imagem."""
    if len(data_url) > (max_bytes * 4 // 3) + 1024:
        raise HTTPException(413, 'Evidência muito grande. Limite de 8 MB após decodificação.')
    supplied_mime = None
    encoded = data_url
    if data_url.startswith('data:'):
        if ',' not in data_url:
            raise HTTPException(422, 'Data URL da imagem inválida.')
        header, encoded = data_url.split(',', 1)
        if header not in ('data:image/png;base64', 'data:image/jpeg;base64'):
            raise HTTPException(415, 'Somente imagens PNG e JPEG são aceitas.')
        supplied_mime = header[5:].split(';', 1)[0]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, 'A evidência não contém Base64 válido.') from exc
    if len(raw) > max_bytes:
        raise HTTPException(413, 'Evidência excede o limite configurado.')
    detected_mime = ('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
                     'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None)
    if not detected_mime or (supplied_mime and detected_mime != supplied_mime):
        raise HTTPException(415, 'Tipo declarado difere do conteúdo; envie PNG ou JPEG válido.')
    try:
        with Image.open(BytesIO(raw)) as img:
            img.verify()
        with Image.open(BytesIO(raw)) as img:
            if img.width * img.height > 20_000_000:
                raise HTTPException(413, 'Imagem com dimensões excessivas.')
            clean = ImageOps.exif_transpose(img).convert('RGB')
            output = BytesIO()
            # Re-encode remove EXIF, GPS, comentários e metadados de arquivos.
            if detected_mime == 'image/png':
                clean.save(output, format='PNG', compress_level=6)
            else:
                clean.save(output, format='JPEG', quality=91, optimize=True)
        sanitized = output.getvalue()
        if len(sanitized) > max_bytes:
            raise HTTPException(413, 'Imagem tratada excede o limite de tamanho.')
        return sanitized, detected_mime
    except HTTPException:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, 'Arquivo de imagem inválido ou danificado.') from exc


def get_catalog() -> ControlCatalog:
    """Inicialização preguiçosa facilita testes e produz erro claro de configuração."""
    if not hasattr(get_catalog, '_cache'):
        get_catalog._cache = load_catalog(settings.resolved_catalog_path, settings.controls_sheet)
    return get_catalog._cache


def get_analyzer() -> GeminiAnalyzer:
    return GeminiAnalyzer(settings.google_api_key, settings.gemini_model, settings.gemini_fallback_model,
                          format_retry=settings.gemini_format_retry)


app = FastAPI(
    title='Cyber Risk Assessment — DATA MASTER',
    version='3.0.0',
    description='Suporte à avaliação humana de controles a partir de evidências visuais.',
)

app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type'],
    )


@app.get('/', include_in_schema=False)
def home():
    return FileResponse(ROOT / 'index.html', media_type='text/html')


@app.get('/health')
def health():
    try:
        catalog = get_catalog()
        return {'status': 'ok', 'controles_carregados': len(catalog.controls),
                'fonte': catalog.source_name, 'versao_catalogo': catalog.digest,
                'colunas_planilha': catalog.source_columns,
                'controles_sem_requisito': catalog.unavailable,
                'integracao_ia_configurada': bool(settings.google_api_key),
                'modelo': settings.gemini_model}
    except (FileNotFoundError, ValueError) as exc:
        return {'status': 'degraded', 'controles_carregados': 0,
                'integracao_ia_configurada': bool(settings.google_api_key),
                'mensagem': str(exc)}


@app.get('/api/controles')
def list_controls(catalog: ControlCatalog = Depends(get_catalog)):
    return catalog.public_list()


@app.get('/api/metadata')
def metadata(catalog: ControlCatalog = Depends(get_catalog)):
    return {'fonte_controles': catalog.source_name, 'versao_catalogo': catalog.digest,
            'colunas_planilha': catalog.source_columns,
            'controles': len(catalog.controls), 'controles_sem_requisito': catalog.unavailable,
            'modelo': settings.gemini_model,
            'versao_prompt': PROMPT_VERSION,
            'modelo_configurado': bool(settings.google_api_key),
            'exemplos_ficticios': catalog.source_name.lower().endswith('.json'),
            'imagem_armazenada': False}



@app.get('/api/demo/cases')
def get_demo_case_list():
    """Cinco cenários fictícios locais; endpoint sem dependência do Gemini."""
    return list_scenarios()


@app.get('/api/demo/imagens/{case_id}')
def demo_image(case_id: str):
    """Somente imagens fixas do pacote; nenhum upload é aceito neste modo."""
    image = get_demo_image(case_id)
    return FileResponse(image, media_type='image/png', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


@app.post('/api/demo/avaliar', response_model=DemoResponse)
def demo_assessment(req: DemoRequest):
    """Retorna texto ilustrativo previamente cadastrado; NÃO chama a IA."""
    return canned_result(req.case_id)


@app.post('/api/auditar', response_model=AuditResponse)
def audit(req: AuditRequest,
          request: Request,
          catalog: ControlCatalog = Depends(get_catalog),
          analyzer: GeminiAnalyzer = Depends(get_analyzer)):
    control = catalog.get(req.controle_id)
    if not control:
        raise HTTPException(404, 'ID não encontrado no catálogo oficial carregado.')
    if not control.disponivel:
        raise HTTPException(422, 'Controle sem requisito aplicável/documentado nesta fonte. Revisão humana necessária.')

    # Nunca confia em um requisito arbitrário vindo do browser.
    if req.politica is not None and req.politica.strip() != control.descricao.strip():
        raise HTTPException(409, 'O requisito apresentado difere do catálogo. Recarregue o controle.')

    if not settings.google_api_key and not app.dependency_overrides.get(get_analyzer):
        raise HTTPException(503, 'IA não configurada. Defina GOOGLE_API_KEY no servidor.')

    image, mime = decode_image(req.imagem_base64, settings.max_image_bytes)
    started = perf_counter()
    try:
        decision: GeminiAnalysis = analyzer.analyze(control.codigo, control.nome, control.descricao, image, mime)
        decision = GeminiAnalysis.model_validate(decision)
    except InvalidModelResponse as exc:
        # Mensagem de erro distingue conteúdo vazio, bloqueio, truncamento e
        # schema inválido sem expor texto do modelo, imagem ou segredo.
        LOGGER.warning('Parecer recusado motivo=%s campos=%s', exc.reason, ','.join(exc.fields) or '-')
        messages = {
            'RESPOSTA_VAZIA': 'O Gemini não gerou conteúdo utilizável. Execute VERIFICAR_GEMINI.bat e tente outra evidência.',
            'RESPOSTA_TRUNCADA': 'O Gemini interrompeu a resposta por limite de saída. Nenhum parecer foi emitido; solicite revisão humana.',
            'RESPOSTA_BLOQUEADA': 'O Gemini bloqueou a geração. Não houve nova tentativa automática; solicite revisão humana.',
            'JSON_INVALIDO': 'O Gemini retornou JSON malformado. Nenhum parecer foi emitido; solicite revisão humana.',
            'CAMPOS_AUSENTES': 'O Gemini deixou campos obrigatórios sem preencher. Nenhum parecer foi emitido; solicite revisão humana.',
            'CAMPOS_INVALIDOS': 'O Gemini retornou valores incompatíveis com o contrato. Nenhum parecer foi emitido; solicite revisão humana.',
            'SCHEMA_INCOMPATIVEL': 'O Gemini retornou uma estrutura incompatível com o parecer. Solicite revisão humana.',
        }
        raise HTTPException(502, {'mensagem': messages.get(exc.reason, 'Parecer inválido. Solicite revisão humana.'),
                                  'codigo': exc.reason, 'campos': list(exc.fields)}) from exc
    except (ValidationError, ValueError) as exc:
        LOGGER.warning('Parecer recusado na validação final tipo=%s', type(exc).__name__)
        raise HTTPException(502, 'O parecer não passou na validação final. Solicite revisão humana.') from exc
    except Exception as exc:
        # Diagnóstico por categoria; nunca expõe mensagem bruta do provedor,
        # credenciais, prompts nem dados de evidências ao navegador ou ao log.
        code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = None
        if isinstance(exc, TimeoutError) or code in (408, 504):
            status, message = 504, 'Tempo limite ao consultar o Gemini. Tente novamente.'
        elif code in (401, 403):
            status, message = 502, ('O Gemini rejeitou a chave ou as permissões de acesso. '
                                    'Confira GOOGLE_API_KEY e o projeto do Google AI Studio.')
        elif code == 404:
            status, message = 502, ('O modelo Gemini configurado não está disponível para a sua chave. '
                                    'Verifique GEMINI_MODEL no arquivo .env e reinicie o servidor.')
        elif code == 429:
            status, message = 429, ('O limite de uso da API Gemini foi atingido. '
                                    'Verifique quota e faturamento e tente novamente mais tarde.')
        elif code == 503:
            status = 503
            if getattr(analyzer, 'attempted_fallback', False):
                message = ('O Gemini retornou HTTP 503 também no modelo alternativo. '
                           'Aguarde e tente novamente; não foi emitido parecer sem análise real.')
            else:
                message = ('O Gemini está temporariamente indisponível (HTTP 503). '
                           'Tente novamente mais tarde ou configure GEMINI_FALLBACK_MODEL no .env '
                           'com um modelo autorizado para sua chave.')
        elif code in (500, 502):
            status = 502
            message = (f'O Gemini retornou erro de servidor HTTP {code}. '
                       'Confira a disponibilidade do serviço e execute VERIFICAR_GEMINI.bat.')
        elif code == 400:
            status, message = 502, ('O Gemini retornou erro HTTP 400. Pode haver incompatibilidade de '
                                    'modelo, parâmetros, schema ou imagem. Execute VERIFICAR_GEMINI.bat '
                                    'para identificar a etapa que falha; confira o modelo disponível para sua chave.')
        else:
            status, message = 502, ('Não foi possível concluir a análise pelo Gemini. '
                                    'Consulte a janela do servidor e confirme as configurações da API.')
        LOGGER.error('Falha Gemini tipo=%s codigo=%s', type(exc).__name__, code)
        raise HTTPException(status, message) from exc

    tier_number = decision.maturidade.nivel
    tier_name, tier_description = TIER[tier_number] if tier_number is not None else (None, None)
    audit_id = uuid4().hex[:12]
    needs_review = (
        decision.desenho.classificacao == 'INSUFICIENTE' or
        decision.implementacao.classificacao == 'NÃO DEMONSTRADO' or
        decision.efetividade.classificacao == 'NÃO CONCLUSIVO' or
        tier_number is None or decision.confianca_ia != 'ALTA' or
        bool(decision.limitacoes_da_evidencia)
    )
    if settings.audit_log_enabled:
        LOGGER.info('audit id=%s controle=%s tier=%s efetividade=%s tempo_ms=%d catalogo=%s prompt=%s',
                    audit_id, control.codigo, tier_number, decision.efetividade.classificacao,
                    round((perf_counter() - started)*1000), catalog.digest, PROMPT_VERSION)

    return AuditResponse(
        id_controle=control.codigo, nome_controle=control.nome,
        **decision.model_dump(),
        nome_tier=tier_name, descricao_tier=tier_description,
        revisao_humana_recomendada=needs_review,
        modelo=getattr(analyzer, 'last_model_used', settings.gemini_model),
        versao_prompt=PROMPT_VERSION, versao_catalogo=catalog.digest, id_analise=audit_id,
    )


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
