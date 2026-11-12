"""Scripted offline examples; no config, credentials, networking, or live models.

The configured strings are preserved only as requested labels. Synthetic catalog
metadata and responses do not establish current availability or real billing.
"""
from collections import defaultdict
import json
import re
from threading import Lock

OWNERS = ('tempest', 'siren', 'alchemist', 'weaver', 'oracle', 'shadow', 'paradox_hunter')
ACTIONS = {'tempest': 'rest', 'siren': 'journal', 'alchemist': 'inquire',
           'weaver': 'library', 'oracle': 'roam', 'shadow': 'inquire', 'paradox_hunter': 'journal'}


def synthetic_catalog(models):
    """Return synthetic API-shaped metadata for pure offline dispatch only."""
    return {'synthetic': True, 'data': [
        {'id': model, 'context_length': 131072,
         'top_provider': {'max_completion_tokens': 4096},
         'supported_parameters': ['max_tokens', 'temperature'],
         'architecture': {'input_modalities': ['text'], 'output_modalities': ['text']},
         'pricing': {'prompt': '0.000001', 'completion': '0.000002', 'request': '0'}}
        for model in sorted(set(models.values()))]}


class ScriptedResponse:
    status_code = 200
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload
    def raise_for_status(self):
        return None


class ScriptedHTTP:
    """Inject as http_post; never substitute this object for an actual provider."""
    def __init__(self):
        self.lock = Lock()
        self.counts = defaultdict(int)
        self.calls = 0

    def __call__(self, _url, *, json=None, **_kwargs):
        payload = json or {}
        text = '\n'.join(str(message.get('content', '')) for message in payload.get('messages', []))
        matched = re.search(r'Stable owner ID:\s*([a-z_]+)', text)
        aid = matched.group(1) if matched else None
        if aid not in OWNERS:
            raise AssertionError('Offline example requires a bounded owner identity')
        with self.lock:
            self.calls += 1
            request_number = self.calls
        is_choice = 'REHEARSAL CHOICE' in text
        if not is_choice and '"action"' in text and '"operation"' not in text:
            is_choice = True
        if is_choice:
            with self.lock:
                self.counts[aid] += 1
                round_number = self.counts[aid]
            action = ACTIONS[aid]
            if round_number == 2 and aid in ('tempest', 'siren'):
                action = 'inquire' if aid == 'tempest' else 'rest'
            command = {'action': action}
            if action == 'library':
                command['query'] = 'contradiction'
            content = __import__('json').dumps(command)
        elif '"operation"' in text or 'operation' in text and ('inquiry' in text.lower()):
            content = __import__('json').dumps({'operation': 'start', 'title': 'A scripted example question',
                      'interpretation': 'This private example is supplied by the offline transport, not authored by a live model.'})
        else:
            content = 'A scripted private example note. No live model produced this record.'
        usage = {'prompt_tokens': 60, 'completion_tokens': 20, 'total_tokens': 80,
                 'prompt_tokens_details': {'cached_tokens': 0},
                 'completion_tokens_details': {'reasoning_tokens': 0}}
        # Some attempts deliberately omit reported costs to exercise unknown coverage.
        if aid != 'oracle':
            usage['cost'] = '0'
        return ScriptedResponse({'id': 'offline-scripted-' + str(request_number),
                                 'model': payload.get('model'), 'provider': 'scripted-offline',
                                 'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
                                 'usage': usage})
