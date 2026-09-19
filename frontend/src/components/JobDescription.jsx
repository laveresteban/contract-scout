import { descriptionToBlocks } from '../utils/description'

// Renders a scraped description as safe, structured plain-text blocks
// (paragraphs and bullet lists). Never injects HTML.
function JobDescription({ html, className }) {
  const blocks = descriptionToBlocks(html)
  if (!blocks.length) return null

  return (
    <div className={className}>
      {blocks.map((block, index) =>
        block.type === 'list' ? (
          <ul key={index} className="description-list">
            {block.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <p key={index}>{block.text}</p>
        )
      )}
    </div>
  )
}

export default JobDescription
