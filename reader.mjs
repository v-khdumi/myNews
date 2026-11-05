export function paginateText(text, fits) {
  const characters = Array.from(new Intl.Segmenter(undefined, { granularity: "grapheme" })
    .segment(text.trim()), (entry) => entry.segment);
  const pages = [];
  let start = 0;
  while (start < characters.length) {
    let low = 1;
    let high = characters.length - start;
    let length = 0;
    while (low <= high) {
      const middle = Math.floor((low + high) / 2);
      if (fits(characters.slice(start, start + middle).join("").trim())) {
        length = middle;
        low = middle + 1;
      } else high = middle - 1;
    }
    if (!length) throw new RangeError("The reader viewport cannot fit one character.");
    let end = start + length;
    if (end < characters.length) {
      let boundary = end;
      while (boundary > start + length * .6 && !/\s/u.test(characters[boundary - 1])) boundary--;
      if (/\s/u.test(characters[boundary - 1])) end = boundary;
    }
    pages.push({ text: characters.slice(start, end).join("").trim(), start, end });
    start = end;
    while (start < characters.length && /\s/u.test(characters[start])) start++;
  }
  return pages;
}
