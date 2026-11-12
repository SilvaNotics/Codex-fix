"""Reviewed display parameters resolved from AST-bounded census evidence."""
PARAMETERS = ('enable_suggested_followups', 'enable_thumbnail_asset')


def reviewed_layers(rows):
    evidence = {name:set() for name in PARAMETERS}
    for row in rows:
        if (row.get('kind') == 'reviewed-display-layer'
                and row.get('review_rule') == 'same-function-learning-data-and-display-sink'
                and row.get('name') in evidence
                and isinstance(row.get('id'),str) and row['id'].isdecimal()):
            evidence[row['name']].add(row['id'])
    return {'layer:'+name:next(iter(ids)) for name,ids in evidence.items() if len(ids)==1}
