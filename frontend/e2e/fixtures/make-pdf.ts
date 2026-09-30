// A minimal, valid single-page PDF (Helvetica Type1 font, BT/ET Tj text operators), built from
// fabricated lines only, so pypdf can extract text from it. Ported from
// backend/tests/resume_fixtures.py::make_text_pdf so the backend's deterministic parser can read
// the result the same way. Every line supplied by callers must be synthetic (CLAUDE.md §Public
// Repository Safety).

function pdfEscape(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')
}

/** Builds a one-page PDF containing `lines`, one per text line, top to bottom. */
export function makeTextPdf(lines: string[]): Buffer {
  const objects: Buffer[] = []
  const addObject = (body: Buffer): number => {
    objects.push(body)
    return objects.length // 1-indexed PDF object number
  }

  const fontObj = addObject(
    Buffer.from('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', 'latin1'),
  )

  const streamLines = ['BT', '/F1 12 Tf', '14 TL', '72 750 Td']
  lines.forEach((line, i) => {
    if (i > 0) streamLines.push('T*')
    streamLines.push(`(${pdfEscape(line)}) Tj`)
  })
  streamLines.push('ET')
  const stream = Buffer.from(streamLines.join('\n'), 'latin1')
  const contentObj = addObject(
    Buffer.concat([
      Buffer.from(`<< /Length ${stream.length} >>\nstream\n`, 'latin1'),
      stream,
      Buffer.from('\nendstream', 'latin1'),
    ]),
  )

  const pagesObjNumber = objects.length + 2 // page object, then pages object
  const pageObj = addObject(
    Buffer.from(
      `<< /Type /Page /Parent ${pagesObjNumber} 0 R /Resources << /Font << /F1 ${fontObj} 0 R >> >> /MediaBox [0 0 612 792] /Contents ${contentObj} 0 R >>`,
      'latin1',
    ),
  )

  const pagesObjActual = addObject(
    Buffer.from(`<< /Type /Pages /Kids [${pageObj} 0 R] /Count 1 >>`, 'latin1'),
  )
  if (pagesObjActual !== pagesObjNumber) {
    throw new Error('internal: pages object number mismatch')
  }

  const catalogObj = addObject(
    Buffer.from(`<< /Type /Catalog /Pages ${pagesObjNumber} 0 R >>`, 'latin1'),
  )

  const chunks: Buffer[] = [Buffer.from('%PDF-1.4\n', 'latin1')]
  const offsets: number[] = [0]
  let offset = chunks[0].length
  objects.forEach((body, index) => {
    const number = index + 1
    offsets[number] = offset
    const chunk = Buffer.concat([
      Buffer.from(`${number} 0 obj\n`, 'latin1'),
      body,
      Buffer.from('\nendobj\n', 'latin1'),
    ])
    chunks.push(chunk)
    offset += chunk.length
  })

  const xrefOffset = offset
  const xrefLines: string[] = [`xref\n0 ${objects.length + 1}\n`, '0000000000 65535 f \n']
  for (let number = 1; number <= objects.length; number++) {
    xrefLines.push(`${offsets[number].toString().padStart(10, '0')} 00000 n \n`)
  }
  chunks.push(Buffer.from(xrefLines.join(''), 'latin1'))
  chunks.push(
    Buffer.from(
      `trailer\n<< /Size ${objects.length + 1} /Root ${catalogObj} 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`,
      'latin1',
    ),
  )

  return Buffer.concat(chunks)
}
