/** The chat dropdown's pick, remembered across reloads and shared by paper and workspace chat. */
export const CHAT_MODEL_KEY = 'paperlab-chat-model'

type ModelStorage = Pick<Storage, 'getItem' | 'setItem'>

/** The model the next question uses: the last pick while it still exists, else the default, else none. */
export function loadChatModel(storage: ModelStorage | undefined, models: { id: string; is_default: boolean }[]): string | null {
  let stored: string | null = null
  try {
    stored = storage?.getItem(CHAT_MODEL_KEY) ?? null
  } catch {
    // Blocked storage: fall back to the default.
  }
  if (stored !== null && models.some((model) => model.id === stored)) return stored
  return models.find((model) => model.is_default)?.id ?? null
}

export function saveChatModel(storage: ModelStorage | undefined, modelId: string): void {
  try {
    storage?.setItem(CHAT_MODEL_KEY, modelId)
  } catch {
    // ponytail: blocked storage only loses the remembered pick.
  }
}
