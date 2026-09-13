import type { Locator } from '@playwright/test'

/** An element's computed fill, e.g. "rgba(74, 222, 128, 0.4)"; retried by callers while styles settle. */
export const backgroundOf = (locator: Locator): Promise<string> =>
  locator.evaluate((element) => getComputedStyle(element).backgroundColor)
