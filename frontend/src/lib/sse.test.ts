import { describe, expect, it } from 'vitest';

import { createSseParser } from './sse';

describe('createSseParser', () => {
  it('parses frames that arrive whole', () => {
    const parser = createSseParser();
    const events = parser.push('event: delta\ndata: {"text":"你好"}\n\n');
    expect(events).toEqual([{ event: 'delta', data: '{"text":"你好"}' }]);
  });

  it('joins a frame split across chunks', () => {
    const parser = createSseParser();
    expect(parser.push('event: del')).toEqual([]);
    expect(parser.push('ta\ndata: {"text":"前')).toEqual([]);
    expect(parser.push('半"}\n')).toEqual([]);
    expect(parser.push('\n')).toEqual([{ event: 'delta', data: '{"text":"前半"}' }]);
  });

  it('handles several frames in one chunk', () => {
    const parser = createSseParser();
    const events = parser.push(
      'event: meta\ndata: {"model":"m"}\n\nevent: delta\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\n',
    );
    expect(events.map((event) => event.event)).toEqual(['meta', 'delta', 'done']);
  });

  it('normalizes CRLF line endings', () => {
    const parser = createSseParser();
    expect(parser.push('event: delta\r\ndata: {"text":"a"}\r\n\r\n')).toEqual([
      { event: 'delta', data: '{"text":"a"}' },
    ]);
  });

  it('keeps a trailing frame buffered until the blank line arrives', () => {
    const parser = createSseParser();
    expect(parser.push('event: done\ndata: {}')).toEqual([]);
    expect(parser.push('\n\n')).toEqual([{ event: 'done', data: '{}' }]);
  });

  it('ignores comments, unknown fields and data-less frames', () => {
    const parser = createSseParser();
    expect(parser.push(': keep-alive\n\n')).toEqual([]);
    expect(parser.push('event: ping\n\n')).toEqual([]);
    expect(parser.push('id: 3\ndata: 完了\n\n')).toEqual([{ event: 'message', data: '完了' }]);
  });

  it('joins multi-line data fields', () => {
    const parser = createSseParser();
    expect(parser.push('data: a\ndata: b\n\n')).toEqual([{ event: 'message', data: 'a\nb' }]);
  });

  it('does not leak state between frames after a partial one', () => {
    const parser = createSseParser();
    parser.push('event: delta\ndata: {"text":"1"}\n\nevent: delta\ndata: {"text"');
    const events = parser.push(':"2"}\n\n');
    expect(events).toEqual([{ event: 'delta', data: '{"text":"2"}' }]);
  });
});
