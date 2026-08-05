import { execSync } from "node:child_process";
import path from "node:path";

// The E2E suite exercises first-run setup, which can only succeed once per
// database (see SetupLock in apps/organizations). `manage.py flush` clears
// all rows but doesn't re-run migrations, and the SetupLock singleton was
// seeded by a data migration rather than a post_migrate signal — so it must
// be re-created explicitly or setup_instance() would crash on a missing row.
export default function globalSetup() {
  // Escape hatch for environments where the Docker CLI isn't available
  // alongside Node (e.g. running the frontend toolchain in a container that
  // doesn't have Docker itself installed) — the operator resets the
  // database from wherever Docker *is* available instead.
  if (process.env.SKIP_E2E_DB_RESET === "true") {
    console.log("SKIP_E2E_DB_RESET=true — assuming the database was already reset externally.");
    return;
  }

  const repoRoot = path.resolve(__dirname, "../..");
  const run = (command: string) =>
    execSync(command, { cwd: repoRoot, stdio: "inherit" });

  run("docker compose exec -T backend python manage.py flush --no-input");
  run(
    "docker compose exec -T backend python manage.py shell -c " +
      `"from apps.organizations.models import SetupLock; SetupLock.objects.get_or_create(id=1)"`,
  );
  // Seeds a dedicated org/users/project for e2e/bug-lifecycle.spec.ts —
  // idempotent and namespaced independently of whatever team-journey.spec.ts
  // or team-project-lifecycle.spec.ts create, so that spec never depends on
  // which spec files ran first (see the command's own docstring).
  run("docker compose exec -T backend python manage.py seed_e2e_bug_fixture");
  // Seeds a dedicated org/users/project/deterministic-bugs fixture for
  // e2e/dashboard.spec.ts — same independence rationale, with fixed
  // relative day-offsets it expects to have available for the whole
  // duration of this Playwright run (see the command's own docstring for
  // the wall-clock-midnight safety margins).
  run("docker compose exec -T backend python manage.py seed_e2e_analytics_fixture");
}
