import { test } from "@e2e-dev/web";
import { expect } from "e2e";

// The page is the output of one real CLI run in offline mode. Every assertion
// reads a data-testid from that report, so the test breaks when the report
// loses a field, not when the prose changes.
test("the HTML report shows the offline verdict and every Then clause", async ({ app, screen }) => {
  await app.open("/");

  await expect(screen.getByTestId("feature")).toContainText("Workspace seat billing");
  await expect(screen.getByTestId("scenario")).toContainText("An admin upgrades a workspace to Pro");
  await expect(screen.getByTestId("verdict-status")).toHaveText("needs_review");
  await expect(screen.getByTestId("verdict-exit-code")).toHaveText("2");
  await expect(screen.getByTestId("model")).toHaveText("not called");
  await expect(screen.getByTestId("unjudged-count")).toHaveText("3");
  await expect(screen.getByTestId("clause-gate")).toHaveText("0.80");
  await expect(screen.getByTestId("verdict-gate")).toHaveText("0.60");
  await expect(screen.getByTestId("verdict-reason")).toContainText("no settled evidence for clause 2, 3, 4");

  const rows = screen.getByTestId("clause-row");
  await expect(rows).toHaveCount(4);

  // Clause 1 carries a declared check, so code decided it and no model ran.
  await expect(rows.nth(0).getByTestId("clause-status")).toHaveText("PASS");
  await expect(rows.nth(0).getByTestId("clause-source")).toHaveText("deterministic");
  await expect(rows.nth(0).getByTestId("clause-text")).toContainText("the workspace plan is Pro");

  // The rest carry no check, so the offline run leaves them unjudged.
  await expect(rows.nth(1).getByTestId("clause-status")).toHaveText("UNJUDGED");
  await expect(rows.nth(1).getByTestId("clause-source")).toHaveText("none");
  await expect(rows.nth(1).getByTestId("clause-score")).toHaveText("-");
  await expect(rows.nth(3).getByTestId("clause-text")).toContainText("no seat is lost");
});
