/** SSE 增量解析：文本块 → 事件。
 *
 *  `fetch` + `ReadableStream` 给出的块不按帧对齐（半帧、一帧里多个事件、CRLF 都可能），
 *  所以这里留一个剩余缓冲，把跨块的半帧拼回来再解析。
 */

export interface SseEvent {
  event: string;
  data: string;
}

export interface SseParser {
  push(chunk: string): SseEvent[];
}

export function createSseParser(): SseParser {
  let rest = '';

  return {
    push(chunk: string): SseEvent[] {
      rest += chunk.replace(/\r\n/g, '\n');
      const parsed: SseEvent[] = [];
      let end = rest.indexOf('\n\n');
      while (end >= 0) {
        const block = rest.slice(0, end);
        rest = rest.slice(end + 2);
        const event = parseBlock(block);
        if (event) parsed.push(event);
        end = rest.indexOf('\n\n');
      }
      return parsed;
    },
  };
}

/** 一帧里的 `event:` 与（可多行的）`data:`；只有注释或没有 data 的帧返回 null。 */
function parseBlock(block: string): SseEvent | null {
  let event = 'message';
  const data: string[] = [];

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      const value = line.slice('event:'.length).trim();
      if (value) event = value;
    } else if (line.startsWith('data:')) {
      data.push(line.slice('data:'.length).replace(/^ /, ''));
    }
  }

  return data.length > 0 ? { event, data: data.join('\n') } : null;
}
