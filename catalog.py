"""Fonte autoritativa do catálogo de controles: JSON fictício ou XLSX privado."""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import re
import unicodedata


@dataclass(frozen=True)
class Control:
    codigo: str
    nome: str
    descricao: str

    @property
    def disponivel(self) -> bool:
        return bool(self.descricao.strip()) and self.descricao.strip().upper() not in {'NA', 'N/A', 'NÃO APLICÁVEL', 'NAO APLICAVEL'}

    def as_dict(self) -> dict:
        return {**asdict(self), 'disponivel': self.disponivel}


def normalize_header(text: object) -> str:
    raw = unicodedata.normalize('NFKD', str(text))
    raw = ''.join(c for c in raw if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', raw.lower())


def split_subcategory(value: str) -> tuple[str, str]:
    """'ID.AM-1: Nome' -> ('ID.AM-1', 'Nome'); evita códigos com descrição."""
    parts = value.strip().split(':', 1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else '')


class ControlCatalog:
    def __init__(self, controls: list[Control], source_name: str, digest: str,
                 source_columns: dict[str, str] | None = None):
        if not controls:
            raise ValueError('Catálogo vazio. Verifique o arquivo e a aba selecionada.')
        self.controls = {c.codigo: c for c in controls}
        if len(self.controls) != len(controls):
            raise ValueError('Foram encontrados IDs duplicados na fonte de controles.')
        self.unavailable = [c.codigo for c in controls if not c.disponivel]
        self.source_name = source_name
        self.digest = digest[:12]
        self.source_columns = source_columns or {}

    def get(self, code: str) -> Control | None:
        return self.controls.get(code)

    def public_list(self) -> list[dict]:
        return [c.as_dict() for c in self.controls.values()]



# Priorizamos os cabeçalhos explícitos, mas mantemos compatibilidade com a
# planilha original do framework e com versões adaptadas para a banca.
_CONTROL_HEADERS = ('controles', 'subcategoria', 'idcontrole',
                    'codigodocontrole', 'codigocontrole', 'idnist')
_REQUIREMENT_HEADERS = ('definicaodecontroles', 'requisitodapoliticaregradenegocio',
                        'requisitodapolitica', 'requisitodocontrole',
                        'requisito', 'definicao', 'evidenciaesperada',
                        'modelodeevidenciaesperada')
_NAME_HEADERS = ('nomedocontrole', 'nomecontrole', 'descricaodocontrole')


def _matching_header(names: list[str], choices: tuple[str, ...]) -> int | None:
    for choice in choices:
        if choice in names:
            return names.index(choice)
    return None


def _load_excel(path: Path, sheet: str) -> tuple[list[Control], dict[str, str]]:
    """Lê colunas CONTROLES ou Sub-categoria e o requisito sem misturá-los.

    Procura a linha dos cabeçalhos em até 30 linhas para aceitar planilhas
    com capa/título antes da tabela; comparações ignoram caixa e acentos.
    """
    import pandas as pd

    scan = pd.read_excel(path, sheet_name=sheet, header=None, nrows=30,
                         keep_default_na=False)
    header_idx = None
    for ix, row in scan.iterrows():
        normalized = [normalize_header(value) for value in row.values]
        if (_matching_header(normalized, _CONTROL_HEADERS) is not None and
                _matching_header(normalized, _REQUIREMENT_HEADERS) is not None):
            header_idx = int(ix)
            break
    if header_idx is None:
        raise ValueError('Não foram localizados os cabeçalhos dos controles e do requisito na aba '
                         f"{sheet!r}. São aceitos CONTROLES ou Sub-categoria e Definição de "
                         'controles ou Requisito da Política. Confira se a aba está correta.')

    df = pd.read_excel(path, sheet_name=sheet, header=header_idx,
                       keep_default_na=False)
    normalized = [normalize_header(col) for col in df.columns]
    ctrl_idx = _matching_header(normalized, _CONTROL_HEADERS)
    req_idx = _matching_header(normalized, _REQUIREMENT_HEADERS)
    name_idx = _matching_header(normalized, _NAME_HEADERS)
    code_column = df.columns[ctrl_idx]
    requirement_column = df.columns[req_idx]
    name_column = df.columns[name_idx] if name_idx is not None else None
    source_columns = {'controles': str(code_column),
                      'requisito': str(requirement_column),
                      'aba': sheet}
    records: list[Control] = []
    invalid_rows: list[str] = []
    for row_no, (_, row) in enumerate(df.iterrows(), start=header_idx + 2):
        raw = str(row[code_column]).strip()
        if not raw:
            continue
        code, name = split_subcategory(raw)
        if not re.fullmatch(r'[A-Z]{2}\.[A-Z]{2,4}-\d+', code):
            # Se CONTROLES for apenas o nome em uma versão da planilha,
            # não adivinhamos o ID nem criamos código inventado.
            invalid_rows.append(f'{row_no}: {raw[:42]}')
            continue
        if not name and name_column is not None:
            name = str(row[name_column]).strip()
        requirement = str(row[requirement_column]).strip()
        records.append(Control(code, name, requirement))
    if not records:
        samples = '; '.join(invalid_rows[:3]) or 'coluna vazia'
        raise ValueError('Nenhum ID NIST válido encontrado na coluna '
                         f"{code_column!r} (ex.: ID.AM-1: Nome). Exemplos: {samples}")
    return records, source_columns


def load_catalog(path: Path, sheet: str = 'PT-BR') -> ControlCatalog:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'Fonte de controles não encontrada: {path}')
    source_columns = {}
    if path.suffix.lower() == '.json':
        raw = json.loads(path.read_text(encoding='utf-8'))
        controls = [Control(str(c['codigo']), str(c['nome']), str(c['descricao'])) for c in raw]
    elif path.suffix.lower() == '.xlsx':
        controls, source_columns = _load_excel(path, sheet)
    else:
        raise ValueError('Fonte inválida: use arquivo JSON de demonstração ou XLSX privado.')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return ControlCatalog(controls, path.name, digest, source_columns)
