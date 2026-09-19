// Turn a scraped HTML job description into readable, structured blocks.
//
// Sources hand us HTML of wildly varying quality. Stripping every tag to a
// single run-on paragraph (the old behaviour) makes responsibilities and
// requirements unreadable. Instead we parse the markup into safe, plain-text
// blocks — paragraphs and bullet lists — and let React render them. We never
// inject raw HTML, so there's no XSS surface.

const ENTITIES = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&#039;': "'",
  '&apos;': "'",
  '&nbsp;': ' ',
  '&mdash;': '—',
  '&ndash;': '–',
  '&bull;': '•',
  '&rsquo;': '’',
  '&lsquo;': '‘',
  '&ldquo;': '“',
  '&rdquo;': '”',
  '&hellip;': '…',
}

function decodeEntities(text) {
  return text
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCharCode(parseInt(code, 16)))
    .replace(/&[a-z]+;|&#0?39;/gi, (match) => ENTITIES[match.toLowerCase()] ?? match)
}

const BULLET_MARK = '' // internal sentinel marking a list item

/**
 * Parse a description into an ordered list of blocks:
 *   { type: 'para', text }        — a paragraph
 *   { type: 'list', items: [...] } — a bullet list
 *
 * @returns {Array<{ type: 'para', text: string } | { type: 'list', items: string[] }>}
 */
export function descriptionToBlocks(html) {
  if (!html) return []

  let text = String(html)

  // Drop non-content elements entirely.
  text = text.replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, '')

  // List items become bullet-marked lines.
  text = text.replace(/<li[^>]*>/gi, `\n${BULLET_MARK}`)

  // Block-level boundaries become paragraph breaks. (Not </li>: consecutive
  // list items should stay in one list, separated by single newlines.)
  text = text.replace(/<\/(p|div|ul|ol|h[1-6]|tr|table|section)>/gi, '\n\n')
  text = text.replace(/<(br|hr)\s*\/?>/gi, '\n')
  text = text.replace(/<\/(h[1-6])>/gi, '\n\n')

  // Strip every remaining tag, then decode entities.
  text = text.replace(/<[^>]+>/g, ' ')
  text = decodeEntities(text)

  // Normalise whitespace within lines but keep line structure.
  const lines = text
    .split('\n')
    .map((line) => line.replace(/[^\S\r\n]+/g, ' ').trim())

  const blocks = []
  let paragraph = []
  let list = []

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: 'para', text: paragraph.join(' ') })
      paragraph = []
    }
  }
  const flushList = () => {
    if (list.length) {
      blocks.push({ type: 'list', items: list })
      list = []
    }
  }

  for (const line of lines) {
    if (!line) {
      flushParagraph()
      flushList()
      continue
    }
    if (line.startsWith(BULLET_MARK) || /^[•\-*·]\s+/.test(line)) {
      flushParagraph()
      const item = line.replace(BULLET_MARK, '').replace(/^[•\-*·]\s+/, '').trim()
      if (item) list.push(item)
    } else {
      flushList()
      paragraph.push(line)
    }
  }
  flushParagraph()
  flushList()

  return blocks
}

// Plain-text length of a description, for "show more" thresholds and quality checks.
export function descriptionTextLength(blocks) {
  return blocks.reduce((sum, block) => {
    if (block.type === 'para') return sum + block.text.length
    return sum + block.items.reduce((s, item) => s + item.length, 0)
  }, 0)
}
