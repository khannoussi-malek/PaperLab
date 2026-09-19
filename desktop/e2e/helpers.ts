/** process.env with every undefined value dropped, so it can be spread into electron.launch()'s env (which takes only
 * string values) alongside each spec's own overrides. */
export const processEnv = () =>
  Object.fromEntries(Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined))
