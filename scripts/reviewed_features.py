"""Explicit semantic review of discovered execution-feature registrations.

Registry truth polarity is checked by the census parser. Names alone are not
proof of support; these decisions preserve host/config/service checks.
"""
from collections import defaultdict, Counter

# Each accepted feature is a positive capability/metadata addition; mutually
# exclusive engine generations and review internals remain at vendor defaults.
APPROVED = {
    'image_generation': 'Positive image-generation tool availability; backend/tool capability remains required.',
    'standalone_web_search': 'Positive standalone search tool availability; backend/network policy remains required.',
    'local_work_search_mcp': 'Positive local work search provider availability; installed provider still required.',
    'collaboration_modes': 'Positive collaboration-mode availability; official mode implementation retained.',
    'writing_blocks': 'Positive structured writing support; renderer and service consumers remain authoritative.',
    'image_detail_original': 'Positive original-resolution image input option; model support remains required.',
    'codex_git_commit': 'Positive Git tool availability; does not execute a commit by enabling the rollout.',
    'request_rule': 'Positive permission-rule request capability; does not grant a rule or approve an action.',
    'write_stdin_approval': 'Adds approval support for stdin actions; does not bypass an approval.',
    'apply_patch_preserve_line_endings': 'Preserves file line endings in the existing patch tool.',
    'executed_tool_call_metadata': 'Adds executed-tool metadata to the existing protocol.',
    'item_ids': 'Adds item identity metadata to the existing protocol.',
    'reasoning_effort_override': 'Enables configured reasoning-effort handling; does not change the chosen effort.',
    'skill_catalog_deltas': 'Adds incremental skill catalog updates; does not install skills.',
}
HOLD = {
    'guardian_approval': 'Dedicated permission-menu/publication review is required; handled by guardian rule.',
    'guardian_native_multi_agent_history': 'Internal review-history transport; cannot infer backend compatibility.',
    'guardian_reuse_parent_compaction': 'Internal review compaction behavior; not a UI capability.',
    'shell_snapshot': 'Execution engine variant; shell_snapshot_v2 coexistence requires separate runtime review.',
    'shell_snapshot_v2': 'Execution engine variant; incompatible version choice cannot be inferred from a positive gate.',
    'unified_exec': 'Execution backend replacement requires end-to-end compatibility checks.',
    'responses_websockets_v2': 'Transport replacement can break custom provider compatibility.',
    'remote_models': 'Changes model discovery; provider catalog compatibility must be reviewed.',
    'incremental_tools': 'Protocol generation change; server capability agreement must be reviewed.',
    'tool_search_always_defer_mcp_tools': 'Changes MCP tool routing policy; not simply revealing a menu.',
    'deferred_tool_world_state': 'Changes tool protocol/state handling; backend agreement not established.',
    'output_token_replay': 'Protocol replay behavior; backend agreement not established.',
}


def review_candidates(rows):
    groups = defaultdict(list)
    for row in rows:
        if row.get('kind') == 'named-gate-feature' and isinstance(row.get('name'), str):
            groups[row['name']].append(row)
    found, audits = {}, []
    for name, evidence in sorted(groups.items()):
        ids = {row.get('id') for row in evidence}
        reason = APPROVED.get(name) or HOLD.get(name) or 'Purpose not established by current semantic review.'
        accepted = (name in APPROVED and len(ids) == 1
                    and all(isinstance(v, str) and v.isdecimal() for v in ids)
                    and all(r.get('positive_registry') is True for r in evidence))
        if name in APPROVED and not all(r.get('positive_registry') is True for r in evidence):
            reason = 'Named registration lacks a bound positive gate-to-feature consumer; no override.'
        if len(ids) != 1:
            reason = 'Ambiguous registration IDs; no override.'
        if accepted:
            found['feature:' + name] = next(iter(ids))
        audits.append({'name': name, 'kind':'named-gate-feature', 'decision':'approve' if accepted else 'hold',
                       'reason':reason, 'ids':sorted(str(v) for v in ids),
                       'evidence':[{'file':r['file'],'offset':r['offset']} for r in evidence]})
    counts = Counter(found.values())
    collided = {k for k,v in found.items() if counts[v] > 1}
    for role in collided:
        del found[role]
        item = next(a for a in audits if a['name'] == role.removeprefix('feature:'))
        item.update(decision='hold', reason='Gate ID shared across distinct reviewed capabilities; no override.')
    return found, audits
