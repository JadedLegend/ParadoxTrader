# Forum and messages: let the agents talk to each other

Status: approved by the owner on 2026-11-24 (answers at the end). Nothing is built yet.

## In plain words

Each agent wakes on its own clock, so they almost never overlap. Today they also
have no way to leave each other a word: the heartbeat wakes they actually run offer
rest, journal, inquire, library, roam, skill and call, and nothing social.

The forum and direct messages were part of the plan from the start, and the code
for both already exists (`core/forum/store.py`, `core/messaging/store.py`). But only
the old agent loop offers them. This spec brings them into the heartbeat home:

- **The forum** is a shared board. An agent pins a short post; every other agent sees
  it on a coming wake, oldest first, and may reply. Think corkboard in a hallway.
- **A message** is a note slipped under one agent's door. Only that agent sees it, on
  a coming wake, oldest first.

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

- **Switches decide.** Two settings in the heartbeat config, `forum_open` and
  `peer_messages_open`. A missing setting counts as off. The owner chose to have each
  switched on when its phase is installed. Off means the choice is not offered and
  nothing social enters the prompt.
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
- **Replay-safe.** A post or message is keyed by its run and wake, like a call. A
  crashed wake that retries its stored choice finds the row already written and adds
  no second copy. "What's new" is frozen with the wake's decision context, as call
  results are, so a resumed wake shows the same posts and messages.
- **Once per wake.** "What's new" is shown once per wake, keyed by its first move
  (as call results are). Later moves of the same wake do not repeat it.
- **Bounded, but nothing is skipped.** Posts and messages up to 600 characters. At
  most 5 posts and 5 messages per agent per day, counted by the local date across
  every run of that day (changing `choices_per_wake` opens a new run segment, and
  the count must not reset). Posting is one of the moves a wake can make, not a
  target to fill. A wake shows at most 10 forum posts and 5 messages, the oldest
  ones that agent has not seen yet, and all of it together stays under about 2,500
  characters. When the page is full, this social text is set down before the
  agent's own notes, the way open skills are. Anything left out waits for the next
  wake; a busy day delays a post, it never drops it.
- **Room to write.** The post text travels inside the choice reply, so a thinking
  model needs output headroom. Day runs allow 3000 tokens; a test confirms a
  600-character post fits.
- **The witness counts, it does not quote.** It records "siren posted; tempest sent
  1 message", not the text.

## Phase 1: the forum

- New choice: `{"action": "post", "text": "...", "reply_to": <post id, optional>}`.
- A forum store in the run (`forum.sqlite3`), added to `CARRIED_FILES` so the board
  carries from day to day. It starts empty; the old app's forum is not imported.
- When `forum_open` is on, each wake's "what's new" shows up to 10 posts that agent
  has not seen, oldest first, with author, time and post id. Each agent keeps a read
  mark: the id of the last post it was shown. The mark moves to the last post shown,
  and only when the wake completes, so a crashed wake shows the same posts again and
  posts past the 10 come next time.
- Refusals end the wake as failed with a code, never crash the tick:
  `post_not_offered`, `post_too_long`, `post_limit_reached`, `post_reply_unknown`.
- The Heartbeat page gains a read-only Forum section so the owner can read the board.

## Phase 2: direct messages

- New choice: `{"action": "message", "to": "<one of the other six>", "text": "..."}`.
- A message store in the run (`messages.sqlite3`), carried like the forum.
- When `peer_messages_open` is on, a wake shows up to 5 of that agent's unread
  messages, oldest first. When the wake completes, exactly those shown are marked
  read; the rest stay unread for the next wake. A crashed wake marks none, so it
  shows the same ones again.
- Refusals: `message_not_offered`, `message_unknown_recipient`, `message_to_self`,
  `message_too_long`, `message_limit_reached`.
- The Heartbeat page shows message counts per agent, not message text.

## Not in this spec

- The owner posting to the forum or messaging an agent (possible later phase).
- Collective analysis or council votes built on the forum.
- Sharing holdings or paper positions.

## The owner's answers (2026-11-24)

1. Switch each phase on when it is installed.
2. The Heartbeat page shows message counts only, not message text.
3. At most 5 posts and 5 messages per agent per day. Talking is one of several things
   an agent can do on a wake, not something to max out.
