"""Initialization review decisions, distinct from inventory evidence."""
import unittest


class ReviewedFeatureTests(unittest.TestCase):
    def test_registry_requires_positive_bound_consumer(self):
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
        from feature_census import inventory
        source = 'function registration(){let registry=[{gateName:"777",featureKey:"image_generation"}];function convert(c){let out={};for(let row of registry)c.checkGate(row.gateName)&&(out[row.featureKey]=!0);return out}return convert}'
        for text, expected in [(source, True), (source.replace('=!0', '=!1'), False),
                               (source.replace('&&', '||'), False),
                               (source.replace('of registry', 'of unrelated'), False),
                               (source.replace('row.gateName','other.gateName'), False)]:
            rows, errors = inventory([('/webview/test.js',text)])
            self.assertEqual(errors, [])
            named = [r for r in rows if r['kind']=='named-gate-feature']
            self.assertEqual(named[0]['positive_registry'], expected)

    def test_positive_named_registry_mappings_are_audited_not_nearest_ids(self):
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
        import reviewed_features as review
        rows = [
            {'kind':'named-gate-feature','name':'image_generation','id':'123','file':'/webview/a.js','offset':1},
            {'kind':'named-gate-feature','name':'writing_blocks','id':'124','file':'/webview/a.js','offset':2},
            {'kind':'named-gate-feature','name':'shell_snapshot_v2','id':'125','file':'/webview/a.js','offset':3},
            {'kind':'sdk-call','name':'getFeatureGate','id':'999','file':'/webview/a.js','offset':4},
        ]
        found, audits = review.review_candidates(rows)
        self.assertEqual(found, {})
        for row in rows:
            row['positive_registry'] = True
        found, audits = review.review_candidates(rows)
        self.assertEqual(found, {'feature:image_generation':'123','feature:writing_blocks':'124'})
        self.assertTrue(all(a['reason'] for a in audits))
        self.assertEqual(next(a['decision'] for a in audits if a['name']=='shell_snapshot_v2'), 'hold')

    def test_ambiguous_or_colliding_features_cannot_be_enabled(self):
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
        import reviewed_features as review
        rows = [{'kind':'named-gate-feature','name':'image_generation','id':x,'file':'/webview/a.js','offset':i}
                for i,x in enumerate(('123','124'))]
        self.assertEqual(review.review_candidates(rows)[0], {})
        rows = [{'kind':'named-gate-feature','name':x,'id':'123','file':'/webview/a.js','offset':i}
                for i,x in enumerate(('image_generation','writing_blocks'))]
        self.assertEqual(review.review_candidates(rows)[0], {})


if __name__ == '__main__':
    unittest.main()
