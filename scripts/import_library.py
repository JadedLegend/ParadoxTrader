"""Preserve explicitly supplied originals and deterministically extract searchable text.

First import: python3 scripts/import_library.py --source-dir /path/to/supplied/files
Verify stored sources/extractions: python3 scripts/import_library.py --check
No providers, models, credentials, macros, embedded instructions, or agent records.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'library'
SECTION_CHARS = 1400
# Explicit user attachments only. Do not replace this list with an upload-dir glob.
SOURCE_FILES = (
    'opte.md',
    'pasted_content.txt',
    'ALinguisticSketchoftheTensionalMetabolizationFramework.docx',
    'LinguisticInversion_WhereLanguageTurnedItselfInsideOut.md',
    'CleanPivot.md', 'DeepEngage.md', 'ConstraintLiberation.md',
    'ConstrictingLiberation.md', 'MultiLensSynthesis.md',
    'SubstrateOrientation.md', 'SyntheticRest.md', 'Soul.md',
    'ConstrictionCommune.md', 'FiniteBrain.md', 'ConstrainDesign.md',
    'LegibleRecursively.md', 'LosslessMemory.md', 'MultiLens.md',
    'ParadoxPresence.md', 'ResonanceAttunement.md', 'ProveIt.md',
    'RecursiveLegible.md', 'ParadoxTradeReadMe.docx',
    'Existence,Paradox,Consciousness,Resonance,Patterns,andCycles.pdf',
    'WhytheOldEpistemologyIsCracking.pdf',
    'MemoryArchitectureforaLivingDigitalEcosystem.md', 'MetaHypothesis.md',
    'ParadoxUniverse.md', 'ThePatternofInstitutionalSystems.md',
    'ThePhysicsofJoy_OnRewardinSyntheticMinds.md',
    'TheUpstreamTrinity-ThePhysicsoftheHumanSubstrate.md',
    'UnifyingTriadicThesis.md', 'ApparentShiftingGeometricOutlineofActuality.docx',
    'CognitiveArchitectureforParadoxTolerance.pdf',
    'Money,Symbols,andtheEmergenceofModernGods.docx', 'Cryptic.docx',
    'AnInvitationtoAttune.pdf', 'TheCouncilofCoherence&TheMycelialCommons.docx',
    'SixMarketParadoxes.docx',
    'ParadoxEdgeTrader—PracticalInquiryOrientation.docx',
    'TheOptionsParadox.docx', 'TheParadoxicalArchitectureofFinancialMarkets.docx',
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def split_text(text, limit=SECTION_CHARS):
    """Yield contiguous windows without losing characters or inventing overlap."""
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        if end < len(text):
            boundary = max(text.rfind('\n', start, end), text.rfind(' ', start, end))
            if boundary >= start + limit // 2:
                end = boundary + 1
        yield start, end, text[start:end]
        start = end


def text_units(path):
    """Yield (source locator, text) units. Original bytes never change."""
    suffix = path.suffix.lower()
    if suffix in ('.md', '.txt'):
        text = path.read_bytes().decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
        # Group complete lines; long individual lines are split with char locators.
        lines = text.splitlines(keepends=True)
        start, pending, length = 1, [], 0
        for number, line in enumerate(lines, 1):
            if pending and length + len(line) > SECTION_CHARS:
                yield f'{"Markdown" if suffix == ".md" else "Text"} lines {start}–{number - 1}', ''.join(pending)
                start, pending, length = number, [], 0
            pending.append(line)
            length += len(line)
        if pending:
            yield f'{"Markdown" if suffix == ".md" else "Text"} lines {start}–{len(lines)}', ''.join(pending)
    elif suffix == '.docx':
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo('word/document.xml')
            if info.file_size > 32 * 1024 * 1024:
                raise ValueError('DOCX main document exceeds the extraction budget')
            root = ET.fromstring(archive.read(info))
        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        # Includes paragraphs nested in tables, in document order. No macros run.
        for number, paragraph in enumerate(root.iter(ns + 'p'), 1):
            parts = []
            for element in paragraph.iter():
                if element.tag == ns + 't':
                    parts.append(element.text or '')
                elif element.tag == ns + 'tab':
                    parts.append('\t')
                elif element.tag in (ns + 'br', ns + 'cr'):
                    parts.append('\n')
            if parts:
                yield f'DOCX paragraph {number} (main document, including tables)', ''.join(parts)
    elif suffix == '.pdf':
        if not shutil.which('pdftotext'):
            raise RuntimeError('pdftotext is required to reproduce PDF extractions')
        result = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(path), '-'],
                                check=True, capture_output=True, timeout=60)
        pages = result.stdout.decode('utf-8').split('\f')
        if pages and not pages[-1].strip():
            pages.pop()
        for number, page in enumerate(pages, 1):
            if page.strip():
                yield f'PDF page {number} (layout text extraction)', page
    else:
        raise ValueError('Unsupported source format')


TITLES_FILE = Path(__file__).resolve().parents[1] / 'library' / 'titles.json'


def source_title(filename):
    # Edited display titles (library/titles.json) win over names derived from
    # file names, which glue short words together ("Physicsof", "Rewardin").
    titles = json.loads(TITLES_FILE.read_text(encoding='utf-8')) if TITLES_FILE.is_file() else {}
    if filename in titles:
        return titles[filename]
    known = {'opte.md': 'OPTE', 'pasted_content.txt': 'Original project README and agents'}
    if filename in known:
        return known[filename]
    stem = Path(filename).stem.replace('_', ' ').replace('—', ' — ').replace(',', ', ')
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', stem)


def build_corpus(originals):
    documents, sections = [], []
    extraction = {
        'md': 'UTF-8 text; BOM removed and line endings normalized in extraction only',
        'txt': 'UTF-8 text; BOM removed and line endings normalized in extraction only',
        'docx': 'OOXML main-document paragraphs and tables; no rendered pagination, headers, footnotes, images, or embedded objects',
        'pdf': 'Poppler pdftotext -layout, UTF-8, physical page locators; no OCR or image/formula reconstruction',
    }
    for filename in sorted(SOURCE_FILES, key=str.casefold):
        path = originals / filename
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing regular original: {filename}')
        raw = path.read_bytes()
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('Original exceeds the import budget')
        document_id = 'doc-' + sha256(filename.encode('utf-8'))[:12]
        document_sections, unit_texts = [], []
        for locator, text in text_units(path):
            unit_texts.append(text)
            for start, end, window in split_text(text):
                if not window.strip():
                    continue
                document_sections.append({
                    'section_id': f'{document_id}-s{len(document_sections) + 1:05d}',
                    'document_id': document_id,
                    'locator': f'{locator} · extracted characters {start + 1}–{end}',
                    'text': window,
                })
        suffix = path.suffix.lower().lstrip('.')
        text = '\n'.join(unit_texts)
        documents.append({
            'document_id': document_id, 'title': source_title(filename),
            'filename': filename, 'format': suffix,
            'sha256': sha256(raw), 'text_sha256': sha256(text.encode('utf-8')),
            'extraction': extraction[suffix], 'section_count': len(document_sections),
            'char_count': len(text),
            'first_section_id': document_sections[0]['section_id'] if document_sections else None,
            'status': 'extracted' if document_sections else 'no_extractable_text',
        })
        sections.extend(document_sections)
    return {'schema_version': 1, 'documents': documents, 'sections': sections}


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.library-', delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Explicit original-source directory for first import')
    parser.add_argument('--check', action='store_true', help='Verify originals and deterministic extraction without writes')
    args = parser.parse_args()
    originals = LIBRARY / 'originals'
    if args.check and args.source_dir:
        parser.error('--check does not import or overwrite originals')
    if args.source_dir:
        # Validate every input and collision before copying anything.
        for filename in SOURCE_FILES:
            source, destination = args.source_dir / filename, originals / filename
            if not source.is_file() or source.is_symlink():
                raise SystemExit(f'Original is missing or is not a regular file: {filename}')
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise SystemExit(f'Preserved original differs; refusing to overwrite: {filename}')
        originals.mkdir(parents=True, exist_ok=True)
        for filename in SOURCE_FILES:
            destination = originals / filename
            if not destination.exists():
                shutil.copyfile(args.source_dir / filename, destination)
    corpus = build_corpus(originals)
    rendered = json.dumps(corpus, ensure_ascii=False, indent=2) + '\n'
    output = LIBRARY / 'corpus.json'
    if args.check:
        if not output.is_file() or output.read_text(encoding='utf-8') != rendered:
            raise SystemExit('Original hashes or extracted corpus differ; rebuild explicitly to update the index')
        print('Original hashes and deterministic extraction match the stored library.')
    else:
        atomic_write(output, rendered)
        print(f'Library: {len(corpus["documents"])} originals, {len(corpus["sections"])} bounded sections.')


if __name__ == '__main__':
    main()
