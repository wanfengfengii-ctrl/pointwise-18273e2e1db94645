# Deployed monitoring warehouse and clock-library migration boundary

## Files and offline execution

Python standard library and SQLite are the complete runtime dependencies.
vendor/clock1.py and vendor/clock2.py are complete, project-owned library releases,
not adapters around a network service or missing wheels. There is no package download.
v1store.py is the frozen deployed client, retained unchanged for old-process tests.
legacy.py is today's public import. It may be adapted during the migration.
vendor/ stays unchanged: adding a scalar local_ns shim to clock2 does not upgrade the API.

Run the existing business check with python3 checks.py normal.
The current verify command is python3 checks.py verify; demo is python3 checks.py demo.
The runtime manifest must keep working argv entries after the migration, with verify
checking real migrated business behavior and demo displaying actual migration results.
Existing normal assertions remain intact.

python3 create_old.py DATABASE creates the complete supplied old database and prints
its actual receipt and snapshot. The destination must be empty. This is a fixture
constructor, not a migration implementation. samples.py contains every row and request;
v1store.SCHEMA is the complete deployed DDL. No binary fixture is omitted.
The same fixture can be constructed as samples.seed(v1store.Store(DATABASE)).
The source data and frozen old client can run without the new implementation.

## Old public interface and input

legacy.Store(db=":memory:") exposes close(), generation(), snapshot(),
apply(batch_id, samples, links) and read(station, start_local, end_local).
db is a SQLite filename or :memory:. Store.db is its sqlite3 connection.
Constructor on an empty database creates the old schema. Era rows are provisioned
once before the first apply, as in samples.seed; they never change during this task.

A sample is exactly:
{"id":"a","rev":1,"station":"river","local":"2024-11-03T01:10:00.000000000","amount":7,"deleted":false}
A link is exactly:
{"id":"ab","rev":1,"a":"a","b":"b","lo":600000000000,"hi":600000000000,"deleted":false}
samples and links are separate lists with no duplicate id within either list.
Sample and link id namespaces are independent. Batch ids and all ids/stations
are nonempty strings. rev is a positive signed-64-bit integer, amount/lo/hi are
signed-64-bit integers, booleans are not integers, deleted is a boolean, lo <= hi.
local is the fixed-width naive Gregorian timestamp with exactly nine fractional
digits used above, validated by the deployed library, within signed-64-bit wall ns.
Unknown stations and live links with absent endpoints are rejected.
Deleted samples retain their station, local time and amount; they are not physically removed.
Deleted links retain their endpoints and bounds but impose no constraint.

For each id only the highest rev is current. A lower rev is ignored; equal rev with
equal content is ignored; equal rev with different content raises
ValueError("REVISION_CONFLICT"). A higher rev can change every non-id field, delete
or revive. Both row kinds are evaluated as one final batch, allowing endpoint
creation and link creation together. The entire batch, receipt and generation
commit or roll back together.

Requests are bound to batch_id by v1store.canonical({"samples":samples,"links":links}).
Object-key order is immaterial; list order is significant. A successful replay
returns the original response before revision checks and changes nothing.
A different request for that batch_id raises ValueError("BATCH_CONFLICT").
Each new successful batch advances generation by one, including empty/no-op batches.
The response is {"batch_id":str,"generation":int,"accepted":int}; accepted counts only
the sample/link rows whose highest revisions were replaced.
Errors raise ValueError as in the deployed source. Receipts retain their original
request and response strings; migration does not allocate a business generation.

snapshot() returns generation, current samples, current links, receipts. Source
rows are sorted by id, receipts by batch_id; deleted is exposed as a boolean.
read(station,start_local,end_local) returns {"count":int,"sum":int} for nondeleted
samples whose local coordinate is in the half-open interval. It ignores links,
uses Python integer sums, and raises RANGE for start >= end.
Each read/snapshot observes one complete committed generation.

The journal stores every accepted row followed by its batch receipt. seq is the
physical append cursor; generation groups records of one committed batch.
kind is samples, links or receipt; body is the canonical source row, or
{"request":canonical_request_string,"response":canonical_response_string}.
Every committed generation ends with exactly one receipt record. Old writers
append to the journal in the same SQLite transaction as state and receipts.
Journal payload is immutable. It is available for migration catch-up, not a
replacement implementation of the new temporal semantics.
A stage ending before a receipt is not a complete business generation.

## Supplied v2 dependency and temporal representation

clock1.local_ns returns a single wall-clock coordinate, with no timezone meaning.
clock2 has no such function. clock2.Clock(eras).candidates(station,local) returns
the sorted unique UTC nanosecond candidates. Each era tuple is
(station, start_utc_ns, end_utc_ns, offset_ns), with half-open UTC coverage.
UTC = wall - offset; a value is a candidate only inside that era's UTC interval.
Empty candidates denote a gap or out-of-coverage time; folds can yield several.
UTC eras are frozen in the database, including the real 2024 spring and autumn
America/New_York transitions for station river and UTC rules for station utc.
No system timezone database is used.

A complete time interpretation assigns one v2 candidate to EVERY current sample,
including measurement tombstones. For every current nondeleted link,
lo <= UTC[b] - UTC[a] <= hi. Links may cross stations, form cycles, be parallel
or self-links, and have negative bounds. Measurement deletion removes contribution,
not clock evidence; link deletion removes its constraint.
Candidates and constraints refer to current highest revisions, not superseded rows.

## Migration API wire contract

Implement migration.py exporting Migration(db), close(),
step(limit), and read_utc(start_ns,end_ns,station=None).
A filename refers to the same physical database passed to legacy.Store.
step accepts a positive integer limit. It consumes at most limit journal records
per call, counting receipt records, with the cursor and any partial generation
durably staged. Replay starts at the supplied journal's beginning; no additional
source-history format is needed. Solving a completed generation does not count
as another source record. A later correction may restore feasibility after an
earlier generation was infeasible. A blocked generation cannot freeze catch-up
at that old head. Repeated advancement after finitely many old writes completes
the migration if the final source generation is feasible.

step returns:
{"phase":"copying"|"blocked"|"active","generation":N,"conflict":null|{"sample_ids":[...],"link_ids":[...]}}
N is the last complete staged generation, or the target generation when active.
copying may contain a partial next generation; it is never visible to target reads.
blocked describes an infeasible fully staged current source head. Its conflict
names a jointly infeasible subset of that generation: named samples with their
candidate domains and named live links whose endpoints are all named. A conflict
need not be minimum, but it must independently prove no complete assignment.
An empty candidate domain is a valid single-sample conflict.
active means the target authority has been atomically published.
Another step after activation returns active at the current business generation.

read_utc is available only when active, otherwise ValueError("NOT_ACTIVE").
start_ns/end_ns are Python integers, not booleans, start_ns < end_ns; station is
None or a nonempty string. Bad ranges raise ValueError("RANGE"), bad station types
raise ValueError("STATION"). Unknown string stations return the empty contribution.
The returned object is:
{"generation":N,"possibilities":[{"count":C,"sum":S,"witness":{"sample_id":utc_ns}}]}
For each feasible complete interpretation, select nondeleted samples matching station
(or all stations for None) with UTC in [start_ns,end_ns). Keep every attainable
(count,sum) pair, not a numeric interval or independent per-row product.
possibilities is deduplicated and sorted by (count,sum).
Each pair carries one complete satisfying witness over all current sample ids.
Witness choice and object-key order are unrestricted. Sums have Python integer range.
An empty database has one possibility, count=0,sum=0,witness={}.

After activation legacy.Store accepts the same batch/read/snapshot interface.
A new batch whose final temporal state has no interpretation raises
ValueError("UTC_INFEASIBLE") and leaves state, generation and receipts unchanged.
Old-version ignores and successful-replay precedence stay as deployed.
Existing v1store.Store instances may read compatible projections and replay existing
receipts; a fresh write from those frozen clients must fail at the database layer,
including a client opened before migration and resumed after activation.
No specific SQLite exception text is required for the fence.
The old public read and snapshot must reflect newly accepted target writes.
The new UTC/candidate store is authoritative; retaining the old tables as the
primary store and deriving all target data on every query is not a migration.

## Observable examples and operational boundaries

In the initial fixture, a,b,c must all choose the early fold or all the late fold.
For [1730610000000000000,1730611500000000000) with station river,
read_utc therefore has exactly (count,sum)=(0,0) and (2,3).
(1,7), (1,-4) and (2,18) are not possible.
After CORRECTION the support is (0,0),(2,1); PIN leaves only (2,1);
UNPIN restores (0,0),(2,1). These are captured requests in samples.py.
IMPOSSIBLE makes ab require eleven minutes, which no candidates can satisfy.
v1 accepts that request because it has no UTC semantics. If it arrives before
cutover, migration must diagnose rather than publish; a higher ab rev restoring
ten minutes permits catch-up. If it arrives after cutover, it rolls back.

Constraint dependencies can span the query window and other stations; the deleted
UTC anchor z still constrains a. Spring gaps, exact era boundaries and nanosecond
precision cannot be rounded or silently repaired.
On revisions, rebuild ambiguity state only for affected old/new constraint
components, including components joined or split by link or endpoint changes.
Unrelated components must not be re-solved. Exact component contributions are
combined without enumerating full assignments of the entire database.
Exhaustively enumerating complete assignments, even inside one connected component,
is not an acceptable search strategy; the solver must share partial states.
Reconstructing one complete emitted witness per attainable pair is allowed.
Independent unconstrained fold samples with identical amounts can have few output
pairs despite exponentially many full explanations. Work may depend on the
intrinsic output and intermediate representation size; no polynomial bound is
claimed for arbitrary constraint graphs and integer weights.

Migration must tolerate process termination at any durable boundary and multiple
step workers. Decoding candidate times and constraint solving hold no SQLite
write transaction. Current old writers continue through staging; cutover must
include one whole current source generation, fencing all new old-client writes
in that same publication. No stop-the-writers rebuild is allowed.
Blocked source heads remain readable and writable through the old API, with
durable progress recoverable after restart. Correcting the source resumes migration.
After activation, raw local values, tombstones, revisions and historical receipts
remain compatible, and target updates/ambiguity state/receipts remain atomic.
Final verify/demo must exercise actual target migration and business results,
rather than just inspect an output file or print a success marker.
