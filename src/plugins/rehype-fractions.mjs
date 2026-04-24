import { visit } from 'unist-util-visit';

const FRACTION_RE = /(\d+)\s*\/\s*(\d+)/g;

/**
 * Rehype plugin that converts fraction strings like "1/2" into formatted
 * <span class="frac"><sup>1</sup>⁄<sub>2</sub></span> elements.
 * Skips <code> and <pre> blocks.
 */
export default function rehypeFractions() {
  return (tree) => {
    visit(tree, 'text', (node, index, parent) => {
      if (!parent) return;
      const tag = parent.tagName;
      if (tag === 'code' || tag === 'pre' || tag === 'script' || tag === 'style') return;

      const text = node.value;
      FRACTION_RE.lastIndex = 0;
      if (!FRACTION_RE.test(text)) return;
      FRACTION_RE.lastIndex = 0;

      const nodes = [];
      let lastIndex = 0;
      let match;

      while ((match = FRACTION_RE.exec(text)) !== null) {
        if (match.index > lastIndex) {
          nodes.push({ type: 'text', value: text.slice(lastIndex, match.index) });
        }
        nodes.push({
          type: 'element',
          tagName: 'span',
          properties: { className: ['frac'] },
          children: [
            { type: 'element', tagName: 'sup', properties: {}, children: [{ type: 'text', value: match[1] }] },
            { type: 'element', tagName: 'span', properties: { 'aria-hidden': 'true' }, children: [{ type: 'text', value: '⁄' }] },
            { type: 'element', tagName: 'sub', properties: {}, children: [{ type: 'text', value: match[2] }] },
          ],
        });
        lastIndex = match.index + match[0].length;
      }

      if (lastIndex < text.length) {
        nodes.push({ type: 'text', value: text.slice(lastIndex) });
      }

      parent.children.splice(index, 1, ...nodes);
      return index + nodes.length;
    });
  };
}
