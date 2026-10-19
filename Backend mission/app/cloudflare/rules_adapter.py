"""Construct the existing pure moderation engine from bundled/D1 data."""
import json
from ..moderation.rules import RuleSet, _Automaton, PATTERNS
from .builtin_words import BUILTIN_WORDS
from .http import require

class CloudRules:
    async def cf_rules(self):
        cached = getattr(self, '_request_rules', None)
        if cached is not None:
            return cached
        raw = await self.db.scalar("SELECT value FROM settings WHERE key='cloud_moderation_rules'")
        try:
            override = json.loads(raw) if raw else {}
            custom = override.get('custom', [])
            disabled = set(override.get('disabled', []))
            require(isinstance(custom, list), '审核配置不可用，请联系管理员', 503)
        except (ValueError, TypeError, AttributeError):
            require(False, '审核配置不可用，请联系管理员', 503)
        rules = RuleSet.__new__(RuleSet)
        rules.custom = custom
        rules.disabled = disabled
        rules.skipped = []
        rules.words = [dict(w) for w in BUILTIN_WORDS if w['word'] not in disabled]
        known = {w['word'] for w in rules.words}
        for entry in custom:
            require(isinstance(entry, dict) and entry.get('action') in ('block', 'review', 'report')
                    and isinstance(entry.get('word'), str) and len(entry['word']) >= 2,
                    '审核配置不可用，请联系管理员', 503)
            if entry['word'] not in known and entry['word'] not in disabled:
                rules.words.append(dict(entry))
                known.add(entry['word'])
        rules.automaton = _Automaton()
        for entry in rules.words:
            rules.automaton.add(entry['word'], entry)
        rules.automaton.build()
        rules.patterns = PATTERNS
        self._request_rules = rules
        return rules
