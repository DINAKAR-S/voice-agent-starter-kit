# Contributing

Thanks for wanting to improve the Voice Agent Starter Kit! This is a template meant to be
forked and adapted — contributions that make it clearer, more correct, or more reusable are welcome.

## Ground rules

1. **Never commit secrets.** No real API keys, SIP credentials, phone numbers, hostnames, VPS IPs,
   Supabase refs, or Telegram tokens — anywhere, including examples and test data. Use the placeholder
   style already in the repo (`YOUR_..._KEY`, `<your-vps-ip>`, `+91XXXXXXXXXX`, `acme-realty`). Real
   values belong only in your local `.env` (which is `.gitignore`d).
2. **Keep the demo generic.** The demo persona is "Maya" for the fictional "Acme Realty". Don't tie
   examples to a real business.
3. **Latency is a feature.** Changes to the prompt/pipeline should keep the hot system prompt short
   (see `docs/04-latency.md`). If a change adds tokens to every turn, say so and justify it.
4. **Be honest about numbers.** Any latency or cost figure must be measured or a cited/dated estimate —
   never a guess presented as fact. Prices are illustrative; mark them "verify current pricing".

## Ways to contribute

- **New language grammar sheets** — add `grammar/maya_<lang>_grammar.md` following the existing 6-section
  structure (register/honorifics, code-mix rule, vocab table, §5b wrong→right, numbers/money, DO/DON'T).
  Native-speaker review strongly preferred — note in the PR whether a native speaker checked it.
- **New use-case templates** — a clinic, a restaurant, a support desk. Swap the persona (`prompts.py`),
  data (`data/*.json`), and tools (`tools.py`); keep it a clean, self-contained example.
- **Provider adapters** — a different STT/TTS/LLM, or a Pipecat variant of the pipeline.
- **Docs fixes, telephony provider notes** (other SIP trunks), dashboard/n8n improvements.

## Before you open a PR

Run the self-checks (they need no API keys):

```bash
python prompts.py            # persona length + grammar wiring
python tools.py              # property-search filters
python deploy/create_sip_trunk.py --self-check
python n8n/recording_handler.py --self-check
python dashboard/build_dashboard.py --self-check
```

- `python dashboard/build_dashboard.py --demo` should render a sample card.
- Grep your diff for anything that looks like a real secret or hostname before committing.

## PR checklist

- [ ] No secrets, real names, hosts, or phone numbers added
- [ ] Self-checks pass
- [ ] Docs updated if behavior or file layout changed
- [ ] Any new price/latency claim is measured or cited + dated

## License

By contributing you agree your contributions are licensed under the repo's [MIT License](LICENSE).
