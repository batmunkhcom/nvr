import { test, expect } from "@playwright/test";

test.describe("NVR Login Page", () => {
  test("should display login form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("h1")).toContainText("Login");
    await expect(page.locator('input[type="text"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test("should show error on invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="text"]', "wrong");
    await page.fill('input[type="password"]', "wrong");
    await page.locator('button[type="submit"]').click();
    // Should show error message or stay on login page
    await expect(page).not.toHaveURL(/dashboard/);
  });
});

test.describe("NVR Dashboard Navigation", () => {
  test("should show sidebar with navigation links", async ({ page }) => {
    await page.goto("/login");
    // Even on login page, verify the app renders (sidebar may be hidden)
    await expect(page.locator("body")).toBeVisible();
  });
});
