#let article(
  title: "",
  author: "",
  date: "",
  url: "",
  body,
) = {
  set document(author: author, title: title)
  set page(
    paper: "us-letter",
    margin: (x: 1.5cm, y: 2cm),
    numbering: "1",
  )
  // set text(font: "Linux Libertine", lang: "en")
  set text(hyphenate: false)
  set par(justify: true)

  show footnote.entry: it => {
    let loc = it.note.location()
    let number = numbering(
      "1",
      ..counter(footnote).at(loc),
    )
    text(size: 0.85em)[
      #super(number)#h(0.4em)#it.note.body
    ]
  }

  show heading: it => {
    set text(weight: "bold")
    block(below: 0.8em, above: 1.2em, it)
  }
  
  show heading.where(level: 1): it => {
    set text(size: 14pt)
    block(below: 1em, it)
  }

  align(center)[
    #text(17pt, weight: "bold")[#title]
    #v(0.5em)
    #text(12pt)[#author]
    #if date != "" [
      #v(0.5em)
      #text(10pt, style: "italic")[#date]
    ]
    #if url != "" [
      #v(0.3em)
      #text(9pt, fill: blue)[#link(url)[#url]]
    ]
  ]

  v(2em)

  columns(2, gutter: 1.5em)[
    #body
  ]
}
