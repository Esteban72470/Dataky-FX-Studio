"""Reviewed names/layouts persist without changing source captures or identities."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import catalog_annotations as review
import fx_tools
import fx_ai_catalog


class CatalogueAnnotations(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'tool').mkdir()
        self.row = {'asset_id':'123','name':'Texture','kind':'flipbook','grid':0,'aliases':['Old'],'tags':[]}
        self.data = {'version':1,'textures':{'123':{'name':'Éclair ramifié','name_observer':'vision','grid_columns':6,'grid_rows':4}}}
        self.write_data()
        (self.root / 'textures.json').write_text(json.dumps([self.row]),encoding='utf-8')

    def write_data(self):
        (self.root / review.DATA_FILE).write_text('DATA = '+repr(self.data),encoding='utf-8')

    def test_name_alias_and_custom_layout_are_idempotent_and_preserve_source(self):
        result = review.apply_annotations([self.row],self.root)[0]
        self.assertEqual(self.row['name'],'Texture')
        self.assertEqual(result['asset_id'],'123')
        self.assertEqual(result['name'],'Éclair ramifié')
        self.assertEqual(result['aliases'],['Old','Texture'])
        self.assertEqual((result['grid_columns'],result['grid_rows']),(6,4))
        self.assertEqual(result['grid'],0)
        self.assertEqual(result['grid_source'],'verified')
        self.assertEqual(review.apply_annotations([result],self.root)[0],result)
        description = fx_tools.describe_asset(result,'textures')
        self.assertEqual(description['flipbook']['FlipbookLayout'],'Custom')

    def test_standard_square_grid_and_unresolved_evidence(self):
        self.data['textures']['123'].update(grid_columns=4,grid_rows=4)
        self.write_data()
        self.assertEqual(review.apply_annotations([self.row],self.root)[0]['grid'],4)
        self.data['textures']['123']={'grid_review_status':'unavailable','grid_review_note':'Aperçu indisponible.'}
        self.write_data()
        result = review.apply_annotations([self.row],self.root)[0]
        self.assertEqual(result['grid'],0)
        self.assertNotIn('grid_columns',result)

    def test_file_is_data_only_and_bounds_layout(self):
        for body in [b'import os\nDATA={}',b'DATA = dict(version=1)',b'DATA={}; print(1)',b'DATA = '+repr({'version':1,'textures':{'123':{'grid_columns':0,'grid_rows':4}}}).encode()]:
            with self.subTest(body=body),self.assertRaises((ValueError,SyntaxError)):
                review.parse_annotations(body)

    def test_cli_and_editor_see_review_changes_without_restarting_or_rewriting_raw_json(self):
        with mock.patch.object(fx_tools,'ROOT',self.root),mock.patch.object(fx_tools,'_catalogs',{}),mock.patch.object(fx_tools,'_catalog_fingerprints',{}):
            self.assertEqual(fx_tools.catalog('textures')[0]['name'],'Éclair ramifié')
            first = fx_ai_catalog.editor_catalog(self.root)
            self.assertEqual(first['textures'][0]['name'],'Éclair ramifié')
            self.data['textures']['123']['name']='Foudre courbe'
            self.write_data()
            second = fx_ai_catalog.editor_catalog(self.root)
            self.assertNotEqual(first['revision'],second['revision'])
            self.assertEqual(second['textures'][0]['name'],'Foudre courbe')
            self.assertEqual(fx_tools.catalog('textures')[0]['name'],'Foudre courbe')
        self.assertEqual(json.loads((self.root/'textures.json').read_text())[0]['name'],'Texture')


if __name__=='__main__':unittest.main()
