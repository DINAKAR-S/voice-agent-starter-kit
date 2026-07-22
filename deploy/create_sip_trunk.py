#!/usr/bin/env python3
"""Create the LiveKit **inbound** SIP trunk + dispatch rule for the voice agent.

Run this ONCE (per DID) after you have LiveKit creds and a Vobiz DID. It wires up
the LiveKit side of the phone path:

    Vobiz DID → Vobiz Origination URI → <project>.sip.livekit.cloud:5060
              → [this inbound trunk] → [this dispatch rule] → agent worker (AGENT_NAME)

    python create_sip_trunk.py            # do it
    python create_sip_trunk.py --dry-run  # just print what would be created

================================================================================
TWO GOTCHAS THAT WILL EAT A DAY IF YOU MISS THEM
================================================================================
1. NO-AUTH INBOUND TRUNK.
   Vobiz's Origination URI carries no SIP auth fields. If this LiveKit trunk has
   auth_username/auth_password set, LiveKit 401s the INVITE and the call never
   connects. So we create the trunk with NO auth. (Auth is only for OUTBOUND /
   transfer legs, which are configured separately.)

2. NUMBER FORMAT.
   Vobiz delivers the called number NATIONAL / 0-prefixed (e.g. 0XXXXXXXXXX),
   NOT E.164. LiveKit matches the inbound trunk on the `numbers` list, so if the
   list only contains +91XXXXXXXXXX the INVITE silently fails with USER_BUSY.
   Fix: put ALL FOUR formats in the list — bare, 0-prefixed, 91-prefixed, +91.
   The expander below does that for you.
================================================================================
"""

import argparse
import asyncio
import os
import sys


def expand_number_formats(did: str) -> list[str]:
    """Return every format Vobiz might present a DID in, for the trunk match list.

    Accepts +91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX or the bare 10-digit number
    and returns all four:  ['XXXXXXXXXX', '0XXXXXXXXXX', '91XXXXXXXXXX', '+91XXXXXXXXXX'].
    """
    digits = did.strip().lstrip("+")
    if digits.startswith("91") and len(digits) == 12:
        national = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        national = digits[1:]
    elif len(digits) == 10:
        national = digits
    else:
        raise ValueError(
            f"Cannot parse DID {did!r}. Expected a 10-digit Indian number in one of: "
            "+91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX, XXXXXXXXXX."
        )
    # Order does not matter to LiveKit; dedupe just in case national already fits.
    return [national, "0" + national, "91" + national, "+91" + national]


def _env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"Missing required env var: {name} (source your .env first)")
    return val


async def _create(dry_run: bool) -> None:
    # Imported lazily so --help and the self-check work without the SDK installed.
    from livekit import api

    did = _env("VOBIZ_DID")
    agent_name = os.environ.get("AGENT_NAME", "maya")
    numbers = expand_number_formats(did)

    print("Will create INBOUND SIP trunk:")
    print(f"  name        : voice-agent-inbound")
    print(f"  numbers     : {numbers}")
    print(f"  auth        : NONE (no-auth — required for Vobiz origination)")
    print("Will create DISPATCH RULE:")
    print(f"  routes calls → agent_name={agent_name!r} in a new room per call")

    if dry_run:
        print("\n--dry-run: nothing was created.")
        return

    # LiveKitAPI reads LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET from env.
    lkapi = api.LiveKitAPI()
    try:
        trunk = await lkapi.sip.create_sip_inbound_trunk(
            api.CreateSIPInboundTrunkRequest(
                trunk=api.SIPInboundTrunkInfo(
                    name="voice-agent-inbound",
                    numbers=numbers,
                    # NO auth_username / auth_password on purpose. See gotcha #1.
                )
            )
        )
        print(f"\nCreated inbound trunk: {trunk.sip_trunk_id}")

        rule = await lkapi.sip.create_sip_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(
                trunk_ids=[trunk.sip_trunk_id],
                rule=api.SIPDispatchRule(
                    # One fresh room per inbound call.
                    dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                        room_prefix="call-"
                    )
                ),
                room_config=api.RoomConfiguration(
                    agents=[api.RoomAgentDispatch(agent_name=agent_name)]
                ),
            )
        )
        print(f"Created dispatch rule : {rule.sip_dispatch_rule_id}")
        print(f"Inbound calls to {did} now route to agent {agent_name!r}. Done.")
    finally:
        await lkapi.aclose()


def _self_check() -> None:
    # The number expander is the one bit of real logic here — verify all 4 formats.
    sample = "+919000000000"  # fake sample DID, digits only for the assertion
    out = expand_number_formats(sample)
    assert out == ["9000000000", "09000000000", "919000000000", "+919000000000"], out
    # Same national number, different input formats → same 4 outputs.
    assert expand_number_formats("09000000000") == out
    assert expand_number_formats("9000000000") == out
    print("self-check OK:", out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="print the plan, create nothing")
    p.add_argument("--self-check", action="store_true", help="run the number-format self-check and exit")
    args = p.parse_args()

    if args.self_check:
        _self_check()
        return
    asyncio.run(_create(args.dry_run))


if __name__ == "__main__":
    main()
