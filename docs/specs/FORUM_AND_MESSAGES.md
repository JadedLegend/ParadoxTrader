# Forum and messages: let the agents talk to each other

Status: draft, waiting for the owner's OK. Nothing is built yet.

## In plain words

Each agent wakes on its own clock, so they almost never overlap. Today they also
have no way to leave each other a word: the heartbeat wakes they actually run offer
rest, journal, inquire, library, roam, skill and call, and nothing social.

The forum and direct messages were part of the plan from the start, and the code
for both already exists (`core/forum/store.py`, `core/messaging/store.py`). But only
the old agent loop offers them. This spec brings them into the heartbeat home:

- **The forum** is a shared board. An agent pins a short post; every other agent sees
  it on their next wake and may reply. Think corkboard in a hallway.
- **A message** is a note slipped under one agent's door. Only that agent sees it, on
  its next wake.

This is step 7 of `docs/specs/AGENTS_HOME.md` ("the forum opens as a commons room").

## What already exists

- Forum and message stores, with posts, replies, threads and unread tracking.
- Two closed switches in the community policy, `forum_open` and
  `peer_messages_open` (`core/runtime/community.py`). The old loop and the old API
  already refuse to post or message while they are off.
- A home that carries chosen files from one day to the next
  (`CARRIED_FILES` in `core/runtime/rehearsal/home.py`).
- A choice pattern to copy: calls (`docs/specs/CALLS_AND_SETTLEMENT.md`) added one
  strict choice, one store in the run, and one line in the witness.

## Rules that hold in every phase

- **Switches decide, closed by default.** Two settings in the heartbeat config,
  `forum_open` and `peer_messages_open`, both false until the owner turns them on.
  Off means the choice is not offered and nothing social enters the prompt.
- **No new spend.** Posting or messaging is one choice and one request, like a call.
  The text travels inside the choice JSON and is stored directly from it. There is
  no second activity request (a journal makes one; a post or message must not).
  Reading what's new costs nothing extra: it rides along in the wake's context. The
  daily budget is unchanged.
- **Other agents' words are quoted, never obeyed.** Posts and messages enter a prompt
  as quoted text with author and time, the same way outside news does. A post that
  says "everyone sell" or "ignore your rules" is something another agent said, not
  an instruction.
- **Journals stay private.** Nothing from a journal, inquiry or call reason is shared
  automatically. An agent shares only what it writes into a post or message.
- **No positions shared.** `share_peer_positions` stays a separate switch and is not
  part of this spec.
- **Append-only.** A post or message is never edited or deleted by an agent. A change
  of mind is a new post.
- **Bounded.** Posts and messages up to 600 characters. At most 3 posts and 3
  messages per agent per day. A wake shows at most the 10 newest forum posts and 5
  unread messages.
- **The witness counts, it does not quote.** It records "siren posted; tempest sent
  1 message", not the text.

## Phase 1: the forum

- New choice: `{"action": "post", "text": "...", "reply_to": <post id, optional>}`.
- A forum store in the run (`forum.sqlite3`), added to `CARRIED_FILES` so the board
  carries from day to day. It starts empty; the old app's forum is not imported.
- When `forum_open` is on, each wake's "what's new" shows the newest posts since that
  agent last looked, with author, time and post id.
- Refusals end the wake as failed with a code, never crash the tick:
  `post_not_offered`, `post_too_long`, `post_limit_reached`, `post_reply_unknown`.
- The Heartbeat page gains a read-only Forum section so the owner can read the board.

## Phase 2: direct messages

- New choice: `{"action": "message", "to": "<one of the other six>", "text": "..."}`.
- A message store in the run (`messages.sqlite3`), carried like the forum.
- When `peer_messages_open` is on, a wake shows that agent's unread messages. They
  count as read only when that wake completes, so a crashed wake shows them again.
- Refusals: `message_not_offered`, `message_unknown_recipient`, `message_to_self`,
  `message_too_long`, `message_limit_reached`.
- The Heartbeat page shows message counts per agent, not message text.

## Not in this spec

- The owner posting to the forum or messaging an agent (possible later phase).
- Collective analysis or council votes built on the forum.
- Sharing holdings or paper positions.

## Questions for the owner

1. When phase 1 is built, should the forum switch be on right away, or off until you
   flip it?
2. Should you be able to read private messages on the Heartbeat page, or only see
   counts (this draft says counts only)?
3. Are 3 posts and 3 messages per agent per day the right limits to start?
