import {
  Bookmark,
  BookmarkCheck,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Share2,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import TurndownService from 'turndown';

import {
  useBulkRead,
  useItem,
  useItemContext,
  useSetItemState,
} from '../../api/hooks';
import { downloadText } from '../../api/client';
import { SourceLogo } from '../../components/Avatar';
import { IconButton } from '../../components/Button';
import { EmptyState } from '../../components/Field';
import { absoluteTime, readingMinutes } from '../../lib/format';
import { sanitizeHtml } from '../../lib/sanitize';
import { strings } from '../../lib/strings';
import type { ReaderSearch } from '../../types';

interface ArticlePaneProps {
  itemId: string | null;
  search: ReaderSearch;
  onNavigate: (itemId: string) => void;
}

const turndown = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced' });

export function ArticlePane({ itemId, search, onNavigate }: ArticlePaneProps) {
  const detail = useItem(itemId);
  const context = useItemContext(itemId, search);
  const setState = useSetItemState();
  const bulkRead = useBulkRead();

  const scroller = useRef<HTMLDivElement | null>(null);
  const [readWords, setReadWords] = useState(0);
  const [flash, setFlash] = useState<string | null>(null);

  const wordCount = detail.data?.word_count ?? 0;
  const html = useMemo(
    () => sanitizeHtml(detail.data?.content_html ?? ''),
    [detail.data?.content_html],
  );

  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
    setReadWords(0);
  }, [itemId]);

  useEffect(() => {
    if (!flash) return;
    const timer = window.setTimeout(() => setFlash(null), 1800);
    return () => window.clearTimeout(timer);
  }, [flash]);

  if (!itemId) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-surface">
        <EmptyState>从左侧选择一篇文章开始阅读</EmptyState>
      </div>
    );
  }

  if (detail.isPending) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-surface text-sm text-ink-3">
        {strings.loading}
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-surface">
        <EmptyState>{strings.error}</EmptyState>
      </div>
    );
  }

  const item = detail.data;
  const progress = wordCount > 0 ? Math.min(1, readWords / wordCount) : 0;

  const onScroll = () => {
    const node = scroller.current;
    if (!node || wordCount === 0) return;
    const max = node.scrollHeight - node.clientHeight;
    const ratio = max <= 0 ? 1 : node.scrollTop / max;
    setReadWords(Math.round(ratio * wordCount));
  };

  const share = async () => {
    const url = item.url ?? window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setFlash(strings.article.linkCopied);
    } catch {
      setFlash(url);
    }
  };

  const exportMarkdown = () => {
    const meta = [
      `# ${item.title}`,
      '',
      `- 来源：${item.feed_title}`,
      item.author ? `- 作者：${item.author}` : null,
      `- 时间：${absoluteTime(item.published_at)}`,
      item.url ? `- 原文：${item.url}` : null,
      '',
      turndown.turndown(html),
    ]
      .filter((line): line is string => line !== null)
      .join('\n');

    downloadText(`${item.title.replace(/[\\/:*?"<>|]/g, '_')}.md`, meta);
  };

  const isEssay = item.kind === 'article';

  return (
    <div className="relative flex h-full min-w-0 flex-1 flex-col bg-surface">
      <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-6 print:hidden">
        {isEssay ? (
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <span className="text-xs text-ink-2">
              {strings.article.progress(readWords, wordCount)}
            </span>
            <span
              role="progressbar"
              aria-valuenow={Math.round(progress * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              className="block h-1 w-full max-w-[704px] overflow-hidden rounded-full bg-line"
            >
              <span
                className="block h-full bg-brand transition-[width]"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </span>
          </div>
        ) : (
          <span className="min-w-0 flex-1" />
        )}

        <div className="flex shrink-0 items-center gap-1">
          <IconButton
            label={item.is_read ? strings.article.markUnread : strings.article.markRead}
            active={item.is_read}
            onClick={() => setState.mutate({ id: item.id, is_read: !item.is_read })}
          >
            {item.is_read ? <CheckCircle2 size={16} /> : <Check size={16} />}
          </IconButton>
          <IconButton
            label={item.is_favorite ? strings.article.unfavorite : strings.article.favorite}
            active={item.is_favorite}
            onClick={() => setState.mutate({ id: item.id, is_favorite: !item.is_favorite })}
          >
            {item.is_favorite ? (
              <BookmarkCheck size={16} className="text-brand" />
            ) : (
              <Bookmark size={16} />
            )}
          </IconButton>
          <IconButton label={strings.article.share} onClick={share}>
            <Share2 size={16} />
          </IconButton>
          <IconButton label={strings.article.exportMarkdown} onClick={exportMarkdown}>
            <FileText size={16} />
          </IconButton>
          <IconButton label={strings.article.exportPdf} onClick={() => window.print()}>
            <Download size={16} />
          </IconButton>
        </div>
      </header>

      <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
        <article className="mx-auto max-w-[660px] px-6 py-8">
          <h1 className="text-3xl font-bold leading-snug text-ink">{item.title}</h1>

          <div className="mt-4 flex flex-wrap items-center gap-2 border-b border-line pb-5 text-xs text-ink-2">
            <SourceLogo name={item.feed_title} iconUrl={item.feed_icon_url} size={20} />
            <span className="font-semibold text-ink">{item.feed_title}</span>
            {item.author ? <span>· {strings.article.author} {item.author}</span> : null}
            <span>· {absoluteTime(item.published_at)}</span>
            {isEssay && wordCount > 0 ? (
              <span>· {strings.article.minutes.replace('{n}', String(readingMinutes(wordCount)))}</span>
            ) : null}
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-auto text-brand-ink underline underline-offset-2"
              >
                {strings.article.openOriginal}
              </a>
            ) : null}
          </div>

          {item.kind === 'video' && item.video_url ? (
            <p className="mt-6">
              <a href={item.video_url} target="_blank" rel="noopener noreferrer">
                {item.channel_name ?? item.feed_title} · {item.video_url}
              </a>
            </p>
          ) : null}

          {item.kind === 'picture' && item.image_url ? (
            <img
              src={item.image_url}
              alt={item.title}
              referrerPolicy="no-referrer"
              className="mt-6 w-full rounded-lg"
            />
          ) : null}

          <div className="article-body mt-6" dangerouslySetInnerHTML={{ __html: html }} />

          <nav className="mt-10 flex items-center justify-between border-t border-line pt-5 print:hidden">
            <IconButton
              label={strings.article.prev}
              size={36}
              disabled={!context.data?.prev_id}
              onClick={() => {
                const prev = context.data?.prev_id;
                if (!prev) return;
                if (!item.is_read) bulkRead.mutate({ ids: [item.id], is_read: true });
                onNavigate(prev);
              }}
            >
              <ChevronLeft size={18} />
            </IconButton>
            <span className="text-xs text-ink-3">
              {(context.data?.index ?? 0) + 1} / {context.data?.total ?? 1}
            </span>
            <IconButton
              label={strings.article.next}
              size={36}
              disabled={!context.data?.next_id}
              onClick={() => {
                const next = context.data?.next_id;
                if (!next) return;
                if (!item.is_read) bulkRead.mutate({ ids: [item.id], is_read: true });
                onNavigate(next);
              }}
            >
              <ChevronRight size={18} />
            </IconButton>
          </nav>
        </article>
      </div>

      {flash ? (
        <div className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-strong px-4 py-2 text-xs text-on-strong shadow-[var(--shadow-pop)]">
          {flash}
        </div>
      ) : null}
    </div>
  );
}
