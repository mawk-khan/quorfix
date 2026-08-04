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
}
