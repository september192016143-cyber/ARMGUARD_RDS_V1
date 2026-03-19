-- =============================================================================
-- ArmGuard RDS V1 — wrk Lua cookie injection script
-- =============================================================================
-- Injects Django session cookies into every wrk request for raw throughput tests.
-- Use this for GET-only authenticated endpoints — it cannot handle CSRF-protected
-- POST requests (use locustfile.py for those).
--
-- Usage (after running auth_session.sh):
--   source /tmp/armguard_session.env
--   wrk -s scripts/stress-test/wrk_auth.lua \
--       -t4 -c50 -d30s --latency \
--       http://<server-ip>/dashboard/
--
-- Thread count (-t): number of OS threads (use CPU cores, e.g. 4)
-- Concurrency (-c):  total open connections (users), e.g. 50
-- Duration (-d):     test duration, e.g. 30s
-- --latency:         print p50/p75/p90/p99 histogram at the end
-- =============================================================================

local cookie = os.getenv("AUTH_COOKIE_HEADER")
local csrf   = os.getenv("CSRF_TOKEN")

-- Fail loudly at startup if the session env var is missing.
-- Running without cookies would only measure the login redirect (302), not real views.
if not cookie or cookie == "" then
    error(
        "AUTH_COOKIE_HEADER env var is not set.\n" ..
        "Run: source <(./scripts/stress-test/auth_session.sh http://<server-ip> USER PASS)\n" ..
        "Then retry wrk."
    )
end

-- wrk calls setup() once per worker thread at startup.
-- Inject cookies here so every request in this thread carries them.
function setup(thread)
    thread:set("cookie", cookie)
    thread:set("csrf",   csrf or "")
end

-- wrk calls init() per thread after setup(). Use it to set headers.
function init(args)
    wrk.headers["Cookie"]      = wrk.thread:get("cookie")
    wrk.headers["X-CSRFToken"] = wrk.thread:get("csrf")
    -- Accept HTML so Django doesn't reject the request as a bot
    wrk.headers["Accept"] = "text/html,application/xhtml+xml"
end

-- Optional: rotate across multiple authenticated URLs for more realistic load.
-- Comment this block out to target a single URL passed on the command line.
local paths = {
    "/dashboard/",
    "/transactions/",
    "/inventory/",
    "/personnel/",
}
local idx = 0

function request()
    idx = (idx % #paths) + 1
    return wrk.format("GET", paths[idx])
end

-- wrk calls response() for each completed response.
-- Log non-200/302 status codes during the run so errors are visible.
function response(status, headers, body)
    if status ~= 200 and status ~= 302 then
        io.write(string.format("[wrk_auth] Unexpected HTTP %d\n", status))
    end
end

-- wrk calls done() once per thread when the test finishes.
-- This is a no-op here — wrk's built-in --latency output is sufficient.
function done(summary, latency, requests)
    -- intentionally empty
end
