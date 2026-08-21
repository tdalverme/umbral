# UMBRAL — Product & System Specification

## 1. Purpose

UMBRAL is a proactive real-estate recommendation system whose goal is not merely to search listings, but to identify properties that are unusually well aligned with each user's preferences, including both explicit requirements and harder-to-express qualitative preferences.

The system should:

- Ingest and normalize property listings from one or more sources.
- Build a rich, reusable representation of each property.
- Model each user's explicit, learned, and temporary preferences.
- Generate and rank candidate listings efficiently.
- Learn from user feedback and behavior.
- Notify users only when a property is meaningfully relevant.
- Support conversational interaction through an agent without delegating core business logic to the language model.
- Remain explainable, auditable, and cost-conscious.

The architecture should separate property understanding, recommendation logic, and conversational reasoning.

---

# 2. Core Design Principles

## 2.1 Separate facts, recommendations, and conversation

UMBRAL must distinguish three different responsibilities:

1. **Property Intelligence**
   - Understands what a property is.
   - Produces reusable facts, observations, inferred features, contextual signals, and semantic representations.
   - Does not know or care which user will consume them.

2. **Recommendation Intelligence**
   - Decides how well a property fits a particular user.
   - Generates candidates, ranks them, learns preferences, and decides whether a recommendation is worth surfacing.
   - Must be primarily deterministic or model-driven in a controlled and testable way.

3. **Agent Intelligence**
   - Interprets user intent.
   - Resolves references from conversation/history.
   - Decides which domain operations should be invoked.
   - Explains results.
   - Must not directly manipulate persistence, scoring rules, or business-critical state.

These three layers may evolve independently.

---

## 2.2 Do not make the agent the system orchestrator

The agent must not be responsible for:

- ingesting listings;
- running enrichment pipelines;
- computing base listing features;
- calculating final ranking scores;
- writing arbitrary data;
- executing arbitrary database operations;
- deciding notification eligibility without using the recommendation layer.

The agent may decide what the user is asking for and which approved operation should be called.

---

## 2.3 Separate listing state, user state, and user-listing state

The system should model three distinct categories of data:

### Listing state
Reusable information about a property.

Examples:

- price;
- area;
- rooms;
- natural light estimate;
- kitchen openness;
- view openness;
- condition;
- contextual neighborhood signals.

This should not be recalculated merely because one user changes preferences.

### User state
What the user values.

Examples:

- hard constraints;
- soft preferences;
- explicit preferences;
- learned preferences;
- semantic preference representation;
- persistent alerts;
- current profile version.

### User-listing state
Information specific to a relationship between one user and one listing.

Examples:

- match score;
- feature contributions;
- notification decision;
- saved/dismissed/contacted status;
- explicit feedback;
- presentation history.

This should only be persisted where useful. The system must not materialize the complete Cartesian product of users × listings.

---

# 3. High-Level System Flow

```text
Listing Sources
      |
      v
Ingestion
      |
      v
Normalization
      |
      +------------------------------+
      |              |               |
      v              v               v
Context         Text/Metadata      Image
Enrichment      Enrichment         Enrichment
      |              |               |
      +--------------+---------------+
                     |
                     v
             Property Representation
                     |
                     v
             Listing Ready / Updated
                     |
                     v
            Candidate Generation
                     |
                     v
                 Ranking
                     |
                     v
           Notification Eligibility
                     |
                     v
      User Experience / Proactive Alert
```

The pipeline must support partial enrichment and progressive availability.

A listing may become searchable before every enrichment stage is complete.

---

# 4. Pipeline Orchestration

## 4.1 Hybrid orchestration model

UMBRAL should use a hybrid model:

### Batch-oriented work
Use periodic/batch execution for work where efficiency is more important than immediate reaction.

Examples:

- periodic listing discovery;
- rechecking active listings;
- detecting listings that disappeared;
- data cleanup;
- backfills;
- bulk model/version migrations;
- offline evaluation;
- analytics;
- recalibration.

### Event-driven work
Use event-driven execution when a change should cause targeted downstream work.

Examples:

- new listing discovered;
- listing normalized;
- listing feature enrichment completed;
- listing price changed;
- listing became inactive;
- user preference changed;
- user feedback recorded;
- listing saved/dismissed/contacted;
- exceptional match detected.

---

## 4.2 Prefer multiple composable pipelines

Do not build one monolithic pipeline that performs every operation from scraping to notification.

Prefer independent stages that progressively enrich the listing.

Conceptually:

```text
listing.discovered
    |
    v
normalize
    |
    v
listing.normalized
    |
    +--> contextual enrichment
    +--> text/metadata enrichment
    +--> image enrichment
    |
    v
listing.enriched
    |
    v
semantic representation
    |
    v
listing.ready
```

Each stage should:

- be independently retryable;
- be idempotent where possible;
- expose completion/failure state;
- avoid requiring unrelated expensive stages to finish;
- be rerunnable for a subset of listings.

---

## 4.3 Progressive enrichment

Listings should support partial state.

Example:

```text
context_enrichment = complete
text_enrichment    = complete
image_enrichment   = pending
semantic_repr      = complete
```

Recommendation logic may use partially enriched listings as long as it accounts for missing data and confidence.

---

# 5. Fast Path vs Async Slow Path

When a user changes a preference, the system should distinguish immediate interaction from broad recomputation.

## 5.1 Fast path

The user-facing path should:

1. interpret the requested change;
2. update session or persistent preference state;
3. retrieve a candidate set;
4. rerank;
5. return updated results quickly.

It must not trigger full re-enrichment of listings.

---

## 5.2 Async slow path

After the immediate response, the system may asynchronously:

- recompute a broader candidate pool;
- refresh cached rankings;
- update notification eligibility;
- update learned preference representations;
- recalculate longer-horizon recommendation state.

The user should not wait for this work to finish before receiving an answer.

---

# 6. Data Persistence Strategy

The system should optimize for current-state access while retaining only history that is useful for audit, learning, debugging, or product behavior.

## 6.1 Current state + selective event history

Prefer:

```text
current entity state
+
compact event history
```

over full snapshots.

### Listing current state
Store the latest normalized representation of each listing.

### Listing event history
Persist meaningful changes such as:

- price changed;
- status changed;
- key structured field changed;
- listing became inactive;
- listing reappeared.

Do not persist full listing snapshots on every periodic refresh unless required for a specific debugging or compliance purpose.

---

## 6.2 User current state

Persist the current user profile separately from user events.

Keep a version identifier so recommendation decisions can be tied to the profile version that produced them.

---

## 6.3 User event history

Persist events that are useful for preference learning and product analysis:

- viewed;
- opened;
- saved;
- dismissed;
- contacted;
- liked;
- disliked;
- revisited;
- explicit feedback;
- preference change.

---

## 6.4 Recommendation audit history

Persist full recommendation decision detail only where it is valuable.

Especially retain:

- notifications sent;
- high-confidence recommendations;
- explicit user interactions;
- recommendation failures worth learning from.

A persisted decision should be able to answer:

> Why did this user receive this listing at this time?

Relevant fields may include:

- user;
- listing;
- final score;
- threshold;
- user profile version;
- ranking version;
- major feature contributions;
- match confidence;
- notification decision;
- reason codes;
- timestamp.

---

# 7. Storage Cost Controls

## 7.1 Avoid persisting all user × listing pairs

Candidate scores should generally be computed on demand or for limited candidate sets.

Persist only:

- top candidates when useful;
- notified matches;
- interacted matches;
- temporary candidate caches.

Temporary candidate state should expire.

---

## 7.2 Raw source data

Raw source artifacts should have bounded retention unless needed longer.

Examples:

- raw page representations;
- raw source payloads;
- transient extraction artifacts.

Normalized data and useful derived features should be retained much longer.

---

## 7.3 Images

Do not assume every source image must be stored indefinitely.

Prefer retaining:

- stable source references where possible;
- compact derived observations;
- image-level metadata;
- hashes;
- feature outputs.

If images are stored locally, expired listings should be eligible for image cleanup after a retention window.

Derived image features should remain even after image deletion if they are still useful.

---

## 7.4 Semantic representations

Only create representations that have demonstrated retrieval or ranking value.

Avoid generating multiple redundant representations for the same listing by default.

---

# 8. Property Intelligence

Property Intelligence converts raw publication data and contextual information into a reusable listing representation.

It must be user-independent.

---

# 9. Property Feature Model

Features should be divided into:

1. **Facts**
2. **Observations**
3. **Perceptual/Inferred Features**
4. **Derived/Contextual Features**

---

## 9.1 Facts

High-confidence values explicitly present in the publication or reliably extracted from structured data.

Examples:

- price;
- currency;
- total area;
- covered area;
- rooms;
- bedrooms;
- bathrooms;
- floor;
- total floors;
- age;
- orientation;
- front/back;
- balcony;
- terrace;
- patio;
- parking;
- storage room;
- elevator;
- amenities;
- expenses;
- location.

---

## 9.2 Observations

Lower-level signals extracted from text, images, plans, or context.

Examples:

- large window visible;
- kitchen and living appear in the same space;
- free wall visible;
- sky visible from balcony;
- opposite building visible;
- living appears rectangular;
- high furniture density;
- bathroom finishes appear old;
- balcony depth appears usable;
- major road nearby;
- nightlife density nearby.

Observations should be preferred as inputs to higher-level inferred concepts.

---

## 9.3 Perceptual / inferred features

These represent useful human concepts inferred from available evidence.

Priority features include:

### Natural light
Possible inputs:

- window presence and size;
- apparent brightness across multiple images;
- floor;
- orientation;
- exterior exposure;
- obstruction;
- visible sky;
- context.

### Kitchen openness
Possible categories/signals:

- separate kitchen;
- semi-integrated kitchen;
- open kitchen;
- kitchenette;
- kitchen-living continuity.

This is expected to be one of the more reliable inferred features.

### Living spaciousness
Represents perceived/functional spaciousness rather than exact room area.

Possible inputs:

- furniture scale;
- free floor area;
- living proportions;
- room width/depth cues;
- circulation;
- total property area;
- number of rooms;
- multiple-image consistency.

Photography distortion should reduce confidence.

### Workspace potential
Represents whether the property appears able to support a practical home-office setup.

Possible inputs:

- free wall;
- visible unused space;
- room proportions;
- bedroom/living flexibility;
- natural light;
- circulation impact.

Possible qualitative output:

- no obvious workspace;
- small desk possible;
- comfortable desk possible;
- dedicated office possible.

### View openness
Possible inputs:

- visible sky;
- opposite-building obstruction;
- approximate distance to obstruction;
- floor;
- balcony/window images;
- urban geometry.

Absence of a view photo must not be treated as evidence of a bad view.

### Visual privacy
Possible inputs:

- opposite building proximity;
- facing windows;
- floor;
- street width;
- balcony exposure;
- ground-floor exposure;
- urban geometry.

This must remain explicitly probabilistic.

### Renovation need
Must separate:

- physical condition;
- aesthetic datedness;
- renovation requirement.

An old-looking property in good condition is not equivalent to a property requiring renovation.

### Residentialness
Should represent how residential the immediate micro-area is.

Possible inputs:

- land use;
- point-of-interest density;
- nightlife;
- road hierarchy;
- traffic;
- commercial density;
- building context;
- green space;
- local urban form.

This should be primarily derived from contextual data rather than subjective language.

### Layout quality
Possible inputs:

- room proportions;
- circulation;
- private/public separation;
- visible dead space;
- room connectivity;
- floor plan when available.

Reliability is substantially higher when a floor plan exists.

### Space efficiency
Possible inputs:

- usable vs circulation space;
- hallways;
- awkward unusable areas;
- room geometry;
- total area;
- floor plan.

This should carry low confidence when no reliable geometry or floor plan exists.

---

# 10. Other Useful Property Signals

The ontology may expand over time, but useful categories include:

## Living / social space

- living size proxy;
- living proportion quality;
- dining capacity;
- sofa layout flexibility;
- hosting potential;
- social living capacity;
- living-balcony connection;
- living natural light.

## Kitchen

- kitchen size;
- kitchen openness;
- kitchen separation;
- counter-space proxy;
- storage proxy;
- natural light;
- ventilation;
- dining-in-kitchen potential;
- kitchen condition.

## Bedrooms

- primary bedroom size proxy;
- bedroom natural light;
- storage;
- room shape;
- privacy;
- noise exposure proxy;
- bed + desk feasibility.

## Exterior

- balcony presence;
- balcony size;
- balcony depth;
- balcony usability;
- balcony furniture capacity;
- balcony privacy;
- balcony sun exposure;
- terrace/patio quality.

## View / openness

- sky visibility;
- green view;
- urban view;
- courtyard view;
- wall-facing penalty;
- obstruction;
- visual privacy.

## Noise / tranquility

Because direct acoustic measurement is usually unavailable, represent this as a proxy.

Possible signals:

- road hierarchy;
- traffic;
- distance to avenues;
- nightlife;
- bus routes;
- railways;
- schools;
- commercial activity;
- floor;
- front/back exposure.

Never present this to users as certain acoustic truth.

## Condition / style

- physical condition;
- modernity;
- aesthetic datedness;
- renovation need;
- kitchen condition;
- bathroom condition;
- visual style representation.

## Building

- building condition;
- common-area condition;
- elevator;
- building age;
- density;
- security/access features;
- amenities.

## Economics

- price per area;
- price relative to comparable listings;
- expenses;
- expenses relative to area/building type;
- days on market;
- price change;
- relative deal attractiveness.

## Location / micro-area

- transit access;
- green-space access;
- commercial access;
- daily-services access;
- nightlife density;
- residentialness;
- traffic exposure;
- street character;
- urban openness.

---

# 11. Feature Representation Requirements

Every inferred or derived feature should support, where applicable:

```text
value
confidence
source
evidence
feature_version
```

Example:

```json
{
  "feature": "view_openness",
  "value": 0.82,
  "confidence": 0.74,
  "source": ["images", "floor", "context"],
  "evidence": [
    "large sky fraction visible",
    "no nearby facade visible from balcony",
    "high floor"
  ]
}
```

---

# 12. Unknown Is a First-Class Value

The system must distinguish:

```text
unknown
neutral
negative
```

Missing evidence must not silently become a neutral score.

Example:

```json
{
  "feature": "visual_privacy",
  "value": null,
  "confidence": 0.10,
  "coverage": "insufficient"
}
```

Ranking should reduce certainty rather than treating this as average privacy.

---

# 13. Observations → Derived Concepts

Whenever practical, avoid asking an inference model to directly produce many opaque final scores.

Prefer:

```text
raw inputs
    |
    v
observable signals
    |
    v
derived concepts
```

Example:

```text
large_window_present
visible_sky_fraction
opposite_building_visible
floor
orientation
        |
        v
natural_light
view_openness
```

Benefits:

- explainability;
- easier debugging;
- feature recalibration without rerunning expensive extraction;
- improved auditability;
- easier training of future feature models.

---

# 14. Feature Reliability Tiers

Suggested initial classification:

## Tier 1 — production-friendly early

- kitchen openness;
- renovation need;
- view openness when evidence exists;
- residentialness.

## Tier 2 — useful with confidence/evidence

- living spaciousness;
- workspace potential;
- visual privacy;
- natural light.

## Tier 3 — require stronger structural evidence

- layout quality;
- space efficiency.

Tier 3 features become substantially more reliable when a floor plan or sufficient geometry is available.

---

# 15. Feature Quality Evaluation

Inferred features do not need perfect absolute numeric calibration to be useful.

The primary requirement is ranking usefulness.

For example, if humans judge:

```text
Listing A feels more spacious than Listing B
```

the important behavior is:

```text
living_spaciousness(A) > living_spaciousness(B)
```

Evaluation should therefore include:

- pairwise ranking accuracy;
- correlation with human judgments;
- calibration where relevant;
- confidence-quality relationship;
- performance by evidence availability.

---

# 16. Evolving the Feature Ontology

Do not attempt to define every possible user preference upfront.

New feature candidates should emerge from repeated user language and recommendation failures.

Example:

```text
repeated user feedback:
"I don't like bathrooms opening directly to the living room"

        |
        v

candidate concept:
bathroom_social_exposure

        |
        v

Can it be inferred reliably?

        |
       yes

        |
        v

Add to feature catalog
        |
        v
Backfill where appropriate
```

A feature should only be added if:

- it appears meaningful to users;
- it can be inferred with acceptable reliability;
- it improves ranking, explanation, or filtering.

---

# 17. Recommendation Intelligence

Recommendation Intelligence combines property representation and user state.

Conceptually:

```text
Property Representation
        +
User Preference Model
        |
        v
Candidate Generation
        |
        v
Ranking
        |
        v
Recommendation / Notification Decision
```

---

# 18. Hard Constraints vs Soft Preferences

## Hard constraints

These eliminate listings.

Examples:

- maximum absolute budget;
- minimum bedrooms;
- acceptable property type;
- excluded areas;
- minimum floor where explicitly required.

## Soft preferences

These affect ranking.

Examples:

- natural light;
- balcony;
- quietness;
- style;
- workspace potential;
- kitchen size;
- living spaciousness;
- residentialness.

The system must not confuse preferences with constraints.

---

# 19. User Preference Model

Maintain at least three conceptual layers.

## 19.1 Explicit persistent preferences

Directly stated or explicitly confirmed by the user.

Examples:

- balcony is important;
- maximum budget;
- prefers bright apartments;
- dislikes highly integrated kitchens.

---

## 19.2 Learned preferences

Inferred from behavior and feedback.

Examples:

- repeatedly saves high-floor listings;
- consistently dismisses dark interiors;
- often contacts listings with usable balconies.

Learned preferences must remain distinguishable from explicit ones.

---

## 19.3 Session overrides

Temporary preferences that only apply to the current search or conversation.

Example:

> "For this search I don't care about balcony."

This must not permanently modify the persistent user profile.

---

# 20. Feedback Learning

## 20.1 Explicit feedback

User language should be interpreted into structured signals.

Example:

> "I like it, but the kitchen is too small and too integrated."

Structured interpretation:

```text
overall sentiment = mixed
kitchen_size      = negative / strong
kitchen_openness  = negative / medium
```

The language model interprets the meaning.

A controlled domain service decides how much the preference model changes.

The language model must not directly assign arbitrary final preference weights.

---

## 20.2 Implicit feedback

Behavioral events may inform learned preferences.

Examples:

- view;
- revisit;
- save;
- dismiss;
- contact;
- repeated engagement.

Do not assume every weak event implies a strong preference.

Behavior should update learned preference evidence gradually.

---

# 21. Candidate Generation

The system must avoid scoring every user against every listing.

Use a staged approach:

```text
all listings
    |
    v
hard filtering
    |
    v
candidate retrieval
    |
    v
fast ranking
    |
    v
deep/top-N ranking
```

Candidate generation may use:

- hard constraints;
- semantic similarity;
- structured preference compatibility;
- recency;
- geographic relevance;
- similarity to liked/saved listings.

---

# 22. Ranking

Ranking should combine multiple interpretable and semantic signals.

Possible dimensions:

- semantic similarity;
- qualitative feature fit;
- location fit;
- price fit;
- visual/style fit;
- learned user preferences;
- freshness;
- novelty;
- confidence.

The exact scoring formulation is an implementation detail and may evolve.

The system must be able to explain the major positive and negative contributors for important recommendations.

---

# 23. User × Listing Features

Some signals must not be stored as intrinsic listing features.

Examples:

- budget fit;
- commute fit;
- distance to personally relevant places;
- style similarity to this user's saved listings;
- visual similarity to this user's liked listings;
- preference-specific feature compatibility.

These are computed from user state + listing state.

---

# 24. Notification Policy

UMBRAL is proactive, but should not become spammy.

A high match score alone must not guarantee a notification.

The notification gate may consider:

- minimum match threshold;
- listing freshness;
- whether the listing was already seen;
- similarity to recently notified listings;
- whether the listing is meaningfully better than existing options;
- user notification budget/frequency;
- listing availability;
- novelty;
- score confidence.

Conceptual example:

```text
match_score > threshold
AND listing_active
AND unseen
AND sufficiently_novel
AND notification_budget_available
AND meaningfully_relevant
        |
        v
SEND
```

---

# 25. Proactive Matching Direction

The system should support both:

```text
user -> listings
```

and:

```text
new/updated listing -> candidate users
```

A newly discovered listing should be able to trigger evaluation against a constrained subset of potentially relevant users.

---

# 26. Agent Intelligence

The agent should have flexible natural-language interpretation but controlled system access.

The agent may:

- interpret intent;
- understand qualitative language;
- resolve references;
- determine whether a preference is persistent or session-only;
- decide which approved tools to invoke;
- explain structured system output;
- ask useful questions when they materially improve recommendation quality.

The agent must not:

- execute arbitrary persistence operations;
- run arbitrary database queries;
- directly modify recommendation weights;
- calculate authoritative match scores itself;
- invent listing facts;
- bypass the recommendation engine;
- independently decide business-critical notification rules.

---

# 27. Agent Tool Contract

The exact names may follow repository conventions. The following describes required capabilities.

## Read tools

### Get user profile
Returns:

- hard constraints;
- explicit preferences;
- learned preferences;
- current profile version;
- relevant semantic profile state.

### Get listing
Returns:

- normalized listing information;
- features;
- confidence;
- evidence;
- relevant images/references;
- current match information where applicable.

### Get recent history
Used to resolve references such as:

- "the one you sent yesterday";
- "the Palermo one";
- "the one I saved".

May query:

- recently presented listings;
- saved listings;
- dismissed listings;
- notifications;
- interaction history.

### Get match explanation
Returns structured recommendation explanation:

- score;
- match confidence;
- strongest positive contributors;
- strongest negative contributors;
- trade-offs.

The agent turns this into natural language.

---

## Search / analysis tools

### Search listings
Accepts:

- hard constraints;
- soft preferences;
- semantic query;
- session overrides;
- optional reference listing;
- result limit.

Returns candidate listings or a candidate-set reference.

### Rerank
Reranks a candidate set using:

- current profile;
- optional session overrides;
- optional search-specific preferences.

### Compare listings
Returns a structured comparison of selected listings against the current user profile.

### Get similar listings
Finds listings similar to a reference property, optionally preserving or relaxing selected dimensions.

---

## Mutation tools

### Update preferences
Accepts semantic changes, not arbitrary raw final weights.

Example:

```json
{
  "changes": [
    {
      "feature": "balcony",
      "direction": "increase",
      "strength": "strong"
    }
  ],
  "source": "explicit_user_statement"
}
```

A controlled domain service applies the actual profile update.

### Record feedback
Stores structured user feedback for a listing.

### Save listing
Marks a listing as saved.

### Dismiss listing
Marks a listing as dismissed.

### Contact listing
Records/initiates the supported contact action.

### Create/modify/pause alert
Manages proactive search intent where applicable.

---

# 28. Example Agent Conversations and Tool Traces

## 28.1 Persistent preference update

User:

> I'd rather accept a slightly smaller apartment if it has a balcony and lots of light.

Agent interpretation:

```text
intent = UPDATE_PREFERENCES
size importance decreases
balcony importance increases
natural-light importance increases
```

Tool sequence:

```text
get_user_profile()
update_preferences(...)
search_listings(...)
rerank(...)
```

Expected behavior:

- persist the preference update;
- create a new profile version;
- return immediately reranked results;
- trigger broader recomputation asynchronously.

---

## 28.2 Listing-specific feedback

User:

> I like this one, but the kitchen looks too small and too integrated with the living room.

Tool sequence:

```text
get_recent_history(...)
get_listing(...)
record_feedback(...)
update_preferences(...)
```

Expected structured interpretation:

```text
sentiment = mixed
kitchen_size = negative / strong
kitchen_openness = negative / medium
```

The system should retain both the listing-specific feedback and the preference-learning signal.

---

## 28.3 Temporary preference

User:

> Show me something like the Belgrano one I saved, but this time I don't care if it has a balcony.

Tool sequence:

```text
get_recent_history(...)
get_similar_listings(
  reference_listing,
  session_override = balcony importance reduced
)
rerank(...)
```

Expected behavior:

- do not modify persistent balcony preference;
- apply the change only to the current search/session.

---

## 28.4 Comparing two listings

User:

> Which is better for me, the Palermo one or the Villa Crespo one you sent today?

Tool sequence:

```text
get_recent_history(...)
compare_listings(...)
get_match_explanation(...) if needed
```

Expected behavior:

- resolve both listings from actual interaction history;
- compare using structured facts and recommendation outputs;
- explain the main trade-offs;
- never invent facts from conversational memory alone.

---

## 28.5 User challenges a recommendation

User:

> Why did you recommend this? It doesn't look like my style at all.

Tool sequence:

```text
get_match_explanation(...)
record_feedback(...) if user is explicitly rejecting it
update_preferences(...) if a durable preference signal is identified
```

Expected response behavior:

- expose why the recommendation scored highly;
- acknowledge the mismatch using real feature contributions;
- convert the rejection into structured learning when appropriate.

---

## 28.6 Complex natural-language search

User:

> I want something in Palermo, Villa Crespo or Colegiales, max 220k. I don't care if it's huge as long as it has lots of light, a balcony and a good living room for having people over. Not first floor.

Agent interpretation:

### Hard
- allowed neighborhoods;
- max price;
- minimum floor.

### Soft
- natural light high;
- balcony high;
- hosting/social living high;
- total size lower importance.

Tool sequence:

```text
search_listings(...)
rerank(...)
get_match_explanation(...) for top results
```

Unless the user indicates permanence, these search-specific preferences should remain session-scoped.

---

## 28.7 Implicit behavior

No agent invocation is required for every event.

Example event sequence:

```text
VIEW listing A
CLOSE listing A

VIEW listing B
SAVE listing B
REVISIT listing B
CONTACT listing B
```

Expected behavior:

- emit behavioral events;
- asynchronously update learned preference evidence;
- keep learned preferences distinguishable from explicit preferences.

---

## 28.8 Proactive recommendation

System event:

```text
NEW_LISTING
```

Flow:

```text
property enrichment
candidate-user retrieval
ranking
notification gate
```

If notification is approved, the agent may generate the human-facing explanation using:

- listing facts;
- match explanation;
- notification context.

The agent does not independently decide that the listing should be sent.

---

# 29. Agent Behavior Rules

The agent should use existing domain state rather than guessing.

Examples:

- If a user references "the one from yesterday", resolve it via history.
- If asked "why did you recommend it?", retrieve the recommendation explanation.
- If a statement clearly says "this time", favor session override over persistent preference.
- If a user expresses a durable preference, persist it through the preference tool.
- If user language is ambiguous but a temporary interpretation is safe, prefer a session-scoped interpretation over prematurely mutating the profile.
- Do not silently turn a soft preference into a hard filter.

---

# 30. Events

The event model should support at least the following conceptual events.

## Listing events

```text
LISTING_DISCOVERED
LISTING_NORMALIZED
LISTING_UPDATED
PRICE_CHANGED
LISTING_ENRICHED
LISTING_READY
LISTING_INACTIVE
LISTING_REACTIVATED
```

## User events

```text
USER_VIEWED_LISTING
USER_SAVED_LISTING
USER_DISMISSED_LISTING
USER_CONTACTED_LISTING
USER_FEEDBACK_RECORDED
USER_PROFILE_UPDATED
USER_ALERT_UPDATED
```

## Recommendation events

```text
CANDIDATE_SET_GENERATED
MATCH_COMPUTED
HIGH_MATCH_DETECTED
NOTIFICATION_APPROVED
NOTIFICATION_SUPPRESSED
NOTIFICATION_SENT
```

Exact event naming may follow existing project conventions.

---

# 31. Idempotency and Reprocessing

Pipeline operations should be safely rerunnable where practical.

A listing should have a stable source identity.

The system must support:

- re-enriching after feature-model changes;
- recomputing only affected features;
- reranking without re-enrichment;
- backfilling new feature definitions;
- retrying failed pipeline stages;
- recomputing recommendation outputs when the user profile changes.

---

# 32. Versioning

Important derived state should be traceable to the version that created it.

Relevant versioned concepts include:

- user profile;
- feature extraction logic/model;
- derived feature definitions;
- semantic representation;
- ranking logic/model;
- notification policy.

The implementation does not need heavyweight versioning infrastructure, but recommendation decisions must remain reproducible enough for debugging.

---

# 33. Explainability

Important recommendations must be explainable through structured evidence.

Example:

```text
match = 0.92

positive:
+ strong natural-light fit
+ usable balcony
+ preferred micro-area
+ good living/hosting potential

negative:
- smaller than ideal
- kitchen openness slightly above preference
```

The natural-language explanation may be generated by the agent, but the underlying reasons must come from structured system output.

---

# 34. Recommendation Failure Signals

The system should track useful failure cases, especially:

```text
high match score
+
explicit user rejection
```

These should be usable for:

- feature calibration;
- preference-model improvement;
- ranking-model evaluation;
- discovery of missing concepts in the feature ontology.

---

# 35. Evaluation

UMBRAL should support offline and online evaluation.

## Property feature evaluation

Evaluate inferred features using:

- human comparison;
- pairwise ranking accuracy;
- confidence calibration;
- performance by evidence availability.

## Recommendation evaluation

Possible metrics:

- save rate;
- dismissal rate;
- contact rate;
- notification engagement;
- high-score rejection rate;
- ranking quality;
- recommendation novelty;
- user-specific precision.

Do not optimize only for clicks if the product goal is exceptional match quality.

---

# 36. Non-Functional Requirements

The implementation should favor:

### Explainability
Important scores and decisions should be traceable.

### Cost awareness
Do not repeatedly recompute expensive listing-level intelligence when only user state changed.

### Incrementality
New features and pipelines should be addable without redesigning the whole system.

### Graceful missing data
Unknown features must not become invented values.

### Idempotency
Pipeline retries should not corrupt state.

### Low user-facing latency
Interactive preference changes should use a fast path.

### Async scalability
Broad recomputation, enrichment, and proactive matching should not block conversations.

### Controlled agent behavior
Business logic must remain behind typed domain operations.

### Auditability
Meaningful notifications and user-facing recommendation decisions should be reconstructible.

---

# 37. Initial Feature Scope

For the first production-quality feature set, prioritize roughly 30–40 strong signals rather than attempting a huge ontology.

Suggested initial scope:

## Objective

- price;
- price per area;
- total area;
- rooms;
- bedrooms;
- bathrooms;
- floor;
- orientation;
- balcony;
- outdoor area;
- expenses;
- building age.

## Spatial / qualitative

- living spaciousness;
- kitchen size;
- kitchen openness;
- workspace potential;
- natural light;
- view openness;
- visual privacy;
- renovation need;
- condition;
- modernity.

## Contextual

- transit access;
- green-space access;
- commercial access;
- nightlife density;
- residentialness;
- quietness proxy.

## Economic

- price vs comparable listings;
- expenses efficiency;
- days on market;
- price change.

## Optional when evidence is strong

- layout quality;
- space efficiency;
- hosting potential;
- balcony usability;
- storage capacity.

---

# 38. Implementation Priorities

The implementation should be staged.

## Phase 1 — Foundations

- normalized listing model;
- property feature model;
- confidence/evidence representation;
- explicit user preferences;
- candidate generation;
- ranking;
- interaction history;
- explanation support.

## Phase 2 — Learning and proactive behavior

- explicit feedback interpretation;
- learned preferences;
- session overrides;
- notification gate;
- proactive listing → user matching.

## Phase 3 — Rich property intelligence

- stronger visual/contextual features;
- observation → derived-feature pipeline;
- feature quality evaluation;
- ontology expansion.

## Phase 4 — Data-driven ranking evolution

As interaction data becomes sufficient:

- use behavioral data for better ranking;
- evaluate more advanced learned ranking;
- retain interpretable contribution/explanation layers.

---

# 39. Definition of Done

The architecture described in this specification is considered implemented when the system can reliably support the following end-to-end behavior:

1. Discover and normalize a new listing.
2. Progressively enrich it with structured, inferred, and contextual features.
3. Represent uncertainty using confidence and unknown values.
4. Make it available to candidate retrieval before every optional enrichment is complete.
5. Match it against relevant users without calculating every user × listing pair.
6. Explain why it ranks highly for a particular user.
7. Decide independently whether it is worth notifying.
8. Send a proactive recommendation only after passing the notification policy.
9. Interpret conversational feedback into structured signals.
10. Distinguish persistent preferences from session-only overrides.
11. Rerank quickly after a user preference change without recomputing listing intelligence.
12. Learn asynchronously from explicit and implicit feedback.
13. Reconstruct why an important recommendation or notification occurred.
14. Expire low-value temporary/raw data without losing important learned signals.
15. Support adding new qualitative features without tightly coupling the rest of the system.

---

# 40. Architectural Boundary Summary

```text
PROPERTY INTELLIGENCE
"What is this property?"
        |
        v
property facts + observations + inferred features
        |
        v
RECOMMENDATION INTELLIGENCE
"How good is this property for this user?"
        |
        v
candidates + scores + trade-offs + notification decision
        |
        v
AGENT INTELLIGENCE
"What is the user trying to do, and how should the system interact?"
```

The central rule is:

> **Property Intelligence produces evidence and property understanding. Recommendation Intelligence produces personalized decisions. Agent Intelligence produces interpretation, tool selection, and conversation.**

Keeping this boundary explicit is a core requirement of UMBRAL.

---

# Appendix A. Notas de adaptacion al repositorio

La presente especificacion fue contrastada contra la arquitectura real de
Umbral (specs 001-018, `CONTEXT.md`, ADRs). Las secciones de la SPEC se
mantienen como contrato de producto; esta nota registra como cada punto se
resuelve en el codigo y los conflictos ya aceptados.

- **NA-01 (unidad de verdad, §2.1/§18/§19)**: la "user profile" de la SPEC se
  implementa como radares (`SearchProfile`) por persona: las preferencias y
  filtros viven por radar, versionados (`ProfileVersion`), no en una entidad
  global de usuario. Decidido en 004/016.
- **NA-02 (session overrides, §19.3/§28.3/§28.6/§29)**: "esta vez" se
  interpreta como edicion del radar (propuesta HITL -> confirmacion ->
  `ProfileVersion`) y la respuesta del agente declara la limitacion
  (durable y reversible). El session scoping real queda diferido. Ver
  `docs/decision-records/0002-session-scoping.md`.
- **NA-03 (fast path, §5/§36)**: el fast path del repo = respuesta inmediata
  con el run previo (flag `stale`) + recomputo async publicado en <30s
  (spec 004). No hay rerank "preview" en V1. Ver ADR 0002.
- **NA-04 (imagenes, §4.3/§9.3/§10/§7.3)**: no hay pipeline de imagenes en
  el stack; V1 enriquece por texto/metadata y contexto urbano. El
  enriquecimiento visual queda en backlog (Fase 3 de §38) con la politica
  de retencion de §7.3.
- **NA-05 (renovation need, §9.3/§37)**: la distincion condicion fisica vs
  datedness estetica se sirve con los conceptos `estado_general` +
  `moderno`; un concepto dedicado solo si el lenguaje de los usuarios lo
  exige (§16).
- **NA-06 (residentialness, §10/§37)**: implementado como concepto
  `calma_residencial` sobre la senal urbana `residential_calm`
  (urban-contract v2).
- **NA-07 (feedback estructurado, §20.1/§28.2/§28.5)**: extension del tool
  `record_feedback` con `concept_feedback[]` (concept_key, polarity,
  strength, confidence) que alimenta el motor de learning proposals
  existente (HITL, 0 auto-apply). Ver
  `docs/decision-records/0003-structured-concept-feedback.md` y
  `specs/019-spec-alignment`.
- **NA-08 (alcance economico, §37)**: `price per area` y `price change`
  entran como conceptos en `specs/019-spec-alignment`; `days on market` y
  `price vs comparable listings` quedan en backlog (requieren recompute
  periodico y stats por barrio respectivamente).
- **NA-09 (direccion proactiva, §25)**: ambas direcciones estan soportadas;
  el planner de notificaciones escanea los items publicados de los radares
  activos (spec 013). El trigger `price_drop` esta declarado pero aun no se
  emite en V1.
- **NA-10 (observacion -> derivado, §13/§38 Fase 3)**: los conceptos se
  extraen directo a observaciones; la capa de features derivadas
  recalcables sin re-extraccion queda diferida a Fase 3.
- **NA-11 (calidad de features, §15/§35)**: la evaluacion por pares con
  humanos queda diferida; V1 se apoya en goldens de extraccion y el
  regression gate de matching (spec 008).
- **NA-12 (DoD §39.9-10)**: el punto 9 queda cubierto por ADR 0003 + 019;
  el punto 10 queda anotado bajo NA-02 (distincion declarada en la
  respuesta del agente, no en un scope de datos propio).
