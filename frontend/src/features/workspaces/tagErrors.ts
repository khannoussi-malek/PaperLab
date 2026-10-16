const TEXT: Record<string, string> = {
  tag_exists: 'A tag with that name already exists.',
  invalid_tag_name: 'Tag names are 1 to 64 characters.',
}

/** The API's error message is the error code; this turns the known ones into plain words. */
export const tagErrorText = (message: string) => TEXT[message] ?? message
