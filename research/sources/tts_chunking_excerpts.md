# How existing voice stacks cut streamed text into speech chunks: saved excerpts (fetched 2026-11-14)

Stars and licences from the GitHub API on 2026-11-14.

## stream2sentence (KoljaB/stream2sentence, 92 stars, Apache-2.0; the text splitter of KoljaB/RealtimeTTS, 4056 stars, Apache-2.0)

From README.md:

- `minimum_sentence_length: int = 10`
  - Minimum character count for a text chunk to be considered a sentence.
  - Shorter fragments are buffered until this threshold is met.
  - Default: 10 characters
- `minimum_first_fragment_length: int = 10`
  - Minimum character count required for the first sentence fragment.
  - Ensures the initial output meets a specified length threshold.
  - Default: 10 characters
### Yield Control
These parameters control how quickly and frequently the generator yields sentence fragments:
- `quick_yield_single_sentence_fragment: bool = False`
  - When True, yields the first fragment of the first sentence as quickly as possible.
  - Useful for getting immediate output in real-time applications like speech synthesis.
  - Default: False
- `quick_yield_for_all_sentences: bool = False`
  - When True, yields the first fragment of every sentence as quickly as possible.
  - Extends the quick yield behavior to all sentences, not just the first one.
  - Automatically sets `quick_yield_single_sentence_fragment` to True.
  - Default: False
- `quick_yield_every_fragment: bool = False`
  - When True, yields every fragment of every sentence as quickly as possible.
  - Provides the most granular output, yielding fragments as soon as they're detected.
  - Automatically sets both `quick_yield_for_all_sentences` and `quick_yield_single_sentence_fragment` to True.

- `sentence_fragment_delimiters: str = ".?!;:,\n…)]}。！？؟।۔-"`
  - Characters considered as potential sentence fragment delimiters.
  - Used for quick yielding of sentence fragments.
  - Default: ".?!;:,\n…)]}。！？؟।۔-"
-
- `preferred_sentence_fragment_delimiters: str[] = ['. ', '? ', '! ', '\n']`
  - Array of strings that delimit a sentence fragment. "Preferred" are checked first and always used if the fragment meets the length requirement over the other fragment delimiters.
  - Note the trailing spaces, added to differentiate between values like $3.5 and a proper sentence end
- `sentence_fragment_delimiters: str[] = ['; ', ': ', ', ', '* ', '**', '– ']`
  - Array of strings that are checked after "preferred" delimiters
- `delimiter_ignore_prefixes: str[]` 
  - Array of strings that will not be considered "delimiters" if preceded by a delimiter.
- `force_first_fragment_after_words: int = 30`
  - Forces the yield of the first sentence fragment after this many words.
  - Ensures timely output even with long opening sentences.
  - Default: 30 words; use `float("inf")` to disable forced word-count yielding.

## LiveKit Agents (livekit/agents, 15217 stars, Apache-2.0), livekit-agents/livekit/agents/tokenize/basic.py

```python
    def __init__(
        self,
        *,
        language: str = "english",
        min_sentence_len: int = 20,
        stream_context_len: int = 10,
        retain_format: bool = False,
    ) -> None:
```

## Pipecat (pipecat-ai/pipecat, 17253 stars, BSD-2-Clause), src/pipecat/utils/string.py: the sentence ends SimpleTextAggregator waits for (Latin and East Asian part)

```python

SENTENCE_ENDING_PUNCTUATION: frozenset[str] = frozenset(
    {
        # Latin script punctuation (most European languages, Filipino, etc.)
        ".",
        "!",
        "?",
        ";",
        "…",
        # East Asian punctuation (Chinese (Traditional & Simplified), Japanese, Korean)
        "。",  # Ideographic full stop
        "？",  # Full-width question mark
        "！",  # Full-width exclamation mark
        "；",  # Full-width semicolon
        "．",  # Full-width period
        "｡",  # Halfwidth ideographic period
        # Indic scripts punctuation (Hindi, Sanskrit, Marathi, Nepali, Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi, Oriya, Assamese)
        "।",  # Devanagari danda (single vertical bar)
```
