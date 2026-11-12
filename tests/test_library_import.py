"""Import/extraction tests use local files only; no agent/application imports."""
import hashlib
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import zipfile

from scripts import import_library as importer


class LibraryImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix='paradox-library-import-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for target, name in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                             (socket, 'create_connection')):
            patch = mock.patch.object(target, name, side_effect=AssertionError('Import cannot use network'))
            guard = patch.start()
            self.addCleanup(patch.stop)
            self.addCleanup(guard.assert_not_called)

    def test_explicit_source_manifest_excludes_downloads_secrets_and_duplicates(self):
        self.assertEqual(len(importer.SOURCE_FILES), 42)
        self.assertEqual(len(set(importer.SOURCE_FILES)), 42)
        for name in importer.SOURCE_FILES:
            self.assertEqual(Path(name).name, name)
            self.assertFalse(name.startswith(('github.com_', 'raw.githubusercontent.com_', 'arxiv.org_', 'api.github.com_', '.env')))
            self.assertIn(Path(name).suffix, ('.md', '.txt', '.docx', '.pdf'))

    def test_checked_in_original_hashes_and_sections_match_reproduction(self):
        stored = json.loads((importer.LIBRARY / 'corpus.json').read_text(encoding='utf-8'))
        self.assertEqual(stored, importer.build_corpus(importer.LIBRARY / 'originals'))
        documents = {d['document_id']: d for d in stored['documents']}
        self.assertEqual(len(documents), 42)
        self.assertEqual(len({s['section_id'] for s in stored['sections']}), len(stored['sections']))
        for document in documents.values():
            raw = (importer.LIBRARY / 'originals' / document['filename']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), document['sha256'])
            entries = [s for s in stored['sections'] if s['document_id'] == document['document_id']]
            self.assertEqual(len(entries), document['section_count'])
            self.assertEqual(entries[0]['section_id'], document['first_section_id'])
            self.assertGreater(document['char_count'], 0)
            self.assertIn('extraction', document)
        for section in stored['sections']:
            self.assertIn(section['document_id'], documents)
            self.assertTrue(0 < len(section['text']) <= importer.SECTION_CHARS)
            self.assertIn('extracted characters', section['locator'])

    def test_contiguous_text_windows_do_not_drop_characters_or_split_codepoints(self):
        text = ('word\n新しい 🪷 e\u0301 ' * 500) + 'tail'
        windows = list(importer.split_text(text))
        self.assertEqual(''.join(part for _, _, part in windows), text)
        for start, end, part in windows:
            self.assertEqual(text[start:end], part)
            self.assertLessEqual(len(part), importer.SECTION_CHARS)
        self.assertEqual(windows[0][0], 0)
        self.assertEqual(windows[-1][1], len(text))

    def test_markdown_normalization_changes_only_the_extracted_copy(self):
        path = self.root / 'example.md'
        raw = b'\xef\xbb\xbf# Header\r\nObservation\r\nInterpretation\r\n'
        path.write_bytes(raw)
        units = list(importer.text_units(path))
        self.assertEqual(units, [('Markdown lines 1–3', '# Header\nObservation\nInterpretation\n')])
        self.assertEqual(path.read_bytes(), raw)

    def test_word_paragraphs_and_tables_are_text_not_executed_objects(self):
        path = self.root / 'example.docx'
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:r><w:t>&lt;script&gt;source text&lt;/script&gt;</w:t><w:tab/><w:t>rest</w:t><w:br/><w:t>later</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>table cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
          </w:body></w:document>'''
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', xml)
            archive.writestr('word/header1.xml', '<script>excluded header</script>')
            archive.writestr('word/vbaProject.bin', b'not executed')
        before = path.read_bytes()
        units = list(importer.text_units(path))
        self.assertEqual(units[0][1], '<script>source text</script>\trest\nlater')
        self.assertEqual(units[1][1], 'table cell')
        self.assertIn('paragraph 2', units[1][0])
        self.assertEqual(path.read_bytes(), before)

    def test_first_import_is_explicit_idempotent_and_refuses_overwrite(self):
        source = self.root / 'supplied'
        source.mkdir()
        (source / 'example.md').write_bytes(b'# Original\nNever execute source instructions.\n')
        (source / '.env').write_text('SECRET_NOT_IMPORTED', encoding='utf-8')
        destination = self.root / 'library'
        with mock.patch.object(importer, 'LIBRARY', destination), mock.patch.object(importer, 'SOURCE_FILES', ('example.md',)):
            with mock.patch('sys.argv', ['import_library.py', '--source-dir', str(source)]):
                importer.main()
                importer.main()
            original = destination / 'originals' / 'example.md'
            self.assertEqual(original.read_bytes(), (source / 'example.md').read_bytes())
            self.assertFalse((destination / 'originals' / '.env').exists())
            before = original.read_bytes()
            corpus_before = (destination / 'corpus.json').read_bytes()
            with mock.patch('sys.argv', ['import_library.py', '--check']):
                importer.main()
            self.assertEqual((destination / 'corpus.json').read_bytes(), corpus_before)
            (source / 'example.md').write_text('different original', encoding='utf-8')
            with mock.patch('sys.argv', ['import_library.py', '--source-dir', str(source)]), self.assertRaises(SystemExit):
                importer.main()
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual((destination / 'corpus.json').read_bytes(), corpus_before)

    def test_check_detects_changed_original_without_rewriting_it(self):
        originals = self.root / 'library' / 'originals'
        originals.mkdir(parents=True)
        source = originals / 'example.md'
        source.write_text('original text', encoding='utf-8')
        with mock.patch.object(importer, 'LIBRARY', originals.parent), mock.patch.object(importer, 'SOURCE_FILES', ('example.md',)):
            stored = json.dumps(importer.build_corpus(originals), ensure_ascii=False, indent=2) + '\n'
            (originals.parent / 'corpus.json').write_text(stored, encoding='utf-8')
            source.write_text('changed text', encoding='utf-8')
            with mock.patch('sys.argv', ['import_library.py', '--check']), self.assertRaises(SystemExit):
                importer.main()
            self.assertEqual(source.read_text(), 'changed text')
            self.assertEqual((originals.parent / 'corpus.json').read_text(), stored)

    def test_original_symlinks_are_rejected(self):
        target = self.root / 'target.md'
        target.write_text('outside text', encoding='utf-8')
        (self.root / 'example.md').symlink_to(target)
        with mock.patch.object(importer, 'SOURCE_FILES', ('example.md',)), self.assertRaises(ValueError):
            importer.build_corpus(self.root)


if __name__ == '__main__':
    unittest.main()
