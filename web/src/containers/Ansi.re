// Copyright 2020 Red Hat, Inc
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

// Ansi renders a log ANSI code to a React component

// Document type
type document = list(atom)
and atom =
  | Text(string)
  | LineBreak
  | DocStyle(ReactDOM.Style.t, document);

type parser('a) = (int, option('a));

open Belt;

module AnsiCode = {
  type code =
    | Clear
    | CarriageReturn
    | Style(ReactDOM.Style.t);

  // Convert a 4 bits color code to its css color: https://en.wikipedia.org/wiki/ANSI_escape_code#3-bit_and_4-bit
  let fourBitColors = (idx: int): option(string) =>
    switch (idx) {
    | 0 => "black"->Some
    | 1 => "red"->Some
    | 2 => "green"->Some
    | 3 => "yellow"->Some
    | 4 => "blue"->Some
    | 5 => "magenta"->Some
    | 6 => "cyan"->Some
    | 7 => "white"->Some
    | _ => None
    };

  // Utility function to convert an option list
  let catMaybes: list(option('a)) => list('a) =
    xs => {
      let rec go = (xs, acc) =>
        switch (xs) {
        | [] => acc
        | [Some(x), ...xs] => xs->go(acc->List.add(x))
        | _ => []
        };
      xs->go([])->List.reverse;
    };

  // Utility functions to create ReactDOM.Style
  let style = x => x->Style->Some;
  let addColor = color => ReactDOM.Style.make(~color, ())->style;
  let addWeight = fontWeight => ReactDOM.Style.make(~fontWeight, ())->style;
  let addStyle = fontStyle => ReactDOM.Style.make(~fontStyle, ())->style;
  let fourBitFgColor = fg =>
    fourBitColors(fg)
    ->Option.flatMap(color => ReactDOM.Style.make(~color, ())->style);
  let fourBitColor = (bg, fg) =>
    fourBitColors(bg)
    ->Option.flatMap(background =>
        fourBitColors(fg)
        ->Option.flatMap(color =>
            ReactDOM.Style.make(~color, ~background, ())->style
          )
      );

  // Parse an ANSI code, returning the length of the sequence
  let parse = (txt: string, pos: int): parser(code) =>
    switch (Js.String.codePointAt(pos, txt)) {
    | Some(0x0a) => (1, CarriageReturn->Some)
    | Some(0x1b) =>
      // escape sequence begin
      let cp = (offset: int): option(int) =>
        Js.String.codePointAt(pos + offset, txt);
      let rec cps = (sz: int, acc: list(option(int))): list(option(int)) =>
        sz <= 0 ? acc : cps(sz - 1, acc->List.add(cp(sz)));
      switch (cps(7, [])->catMaybes) {
      // interpret sequence
      | [91, 48, 48, 109, ..._] => (5, Clear->Some)
      | [91, 48, 49, 109, ..._] => (5, "bold"->addWeight)
      | [91, 48, 51, 109, ..._] => (5, "italic"->addStyle)
      | [91, 48, 49, 59, 51, fg, 109] => (8, fourBitFgColor(fg - 48))
      | [91, 52, bg, 59, 51, fg, 109] => (8, fourBitColor(bg - 48, fg - 48))
      | xs =>
        Js.log2("Unknown ANSI sequence:", xs->List.toArray);
        (1, None);
      };
    | _ => (0, None)
    };
};

module Document = {
  let text = (txt: string, from: int, to_: int): atom =>
    txt->Js.String.slice(~from, ~to_)->Text;

  // Parse a document
  let parse = (txt: string, length: int, pos: int): parser(document) => {
    let rec go = (pos: int, prev: int) =>
      switch (pos == length, txt->AnsiCode.parse(pos)) {
      // we reached the end of the txt
      | (true, _) => (pos, [text(txt, prev, pos)]->Some)
      // current codepoint is an escape sequence
      | (_, (length, Some(code))) =>
        let prevElem = txt->text(prev, pos);
        let pos = pos + length;
        switch (code) {
        | Clear => (pos, [prevElem]->Some)
        | CarriageReturn => (pos, [prevElem, LineBreak]->Some)
        | Style(style) =>
          // recursively parse the stylized block
          let (pos, Some(styled)) = go(pos, pos);
          (pos, [prevElem, DocStyle(style, styled)]->Some);
        };
      // otherwise we keep on parsing
      | (_, (_, None)) => go(pos + 1, prev)
      };
    pos->go(pos);
  };
};

// Convert a string to a document
let rec parse = (txt: string): document => {
  let length = txt->Js.String.length;
  switch (txt->Document.parse(length, 0)) {
  | (pos, Some(doc)) =>
    pos == length
      // when input is fully parsed, return the document
      ? doc
      // otherwise add the remaining
      : doc->List.concat(txt->Js.String.sliceToEnd(~from=pos)->parse)
  | _ => []
  };
};

// Convert a document to a React.element
let render = (doc: document): React.element => {
  let rec go = (xs: document, acc: list(React.element)): React.element =>
    switch (xs) {
    | [] => acc->List.reverse->List.toArray->ReasonReact.array
    | [LineBreak, ...xs] => xs->go(acc->List.add(<br />))
    | [Text(txt), ...xs] => xs->go(acc->List.add(txt->React.string))
    | [DocStyle(style, elems), ...xs] =>
      xs->go(acc->List.add(<span style> {elems->go([])} </span>))
    };
  doc->go([]);
};

// The react component
[@react.component]
let make = (~log: string) => {
  <div> {log->parse->render} </div>;
};

let default = make;
