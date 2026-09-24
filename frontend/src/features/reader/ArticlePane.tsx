import {
  Bookmark,
  BookmarkCheck,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Download,
  FileText,
  Loader2,
  Languages,
  Share2,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import TurndownService from 'turndown';

import {
  useAiConfig,
  useAiResults,
  useBulkRead,
  useGenerateAi,
  useItem,
  useItemContext,
  useSetItemState,
} from '../../api/hooks';
import { downloadText } from '../../api/client';
import { SourceLogo } from '../../components/Avatar';
import { IconButton } from '../../components/Button';
import { EmptyState } from '../../components/Field';
import { absoluteTime, readingMinutes } from '../../lib/format';
import { mediaUrl } from '../../lib/media';
import { sanitizeHtml } from '../../lib/sanitize';
import { useI18n, useT } from '../../lib/i18n';
import type { ReaderSearch } from '../../types';

interface ArticlePaneProps {
  itemId: string | null;
  search: ReaderSearch;
  onNavigate: (itemId: string) => void;
}

const turndown = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced' });

export function ArticlePane({ itemId, search, onNavigate }: ArticlePaneProps) {
  const t = useT();
  const { locale } = useI18n();
  const detail = useItem(itemId);
  const context = useItemContext(itemId, search);
  const setState = useSetItemState();
  const bulkRead = useBulkRead();

  const scroller = useRef<HTMLDivElement | null>(null);
  const [readWords, setReadWords] = useState(0);
  const [flash, setFlash] = useState<string | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(true);

  const aiConfig = useAiConfig();
  const aiResults = useAiResults(itemId);
  const generateAi = useGenerateAi();

  const aiReady = (aiConfig.data?.providers ?? []).some((provider) => provider.enabled);
  const summary = aiResults.data?.summary ?? null;
  const translatedTitle = aiResults.data?.title_translation ?? null;

  const wordCount = detail.data?.word_count ?? 0;
  const html = useMemo(
    // 传原文地址：正文里的相对图片路径要按它解析，否则会被当成本站路径
    () => sanitizeHtml(detail.data?.content_html ?? '', detail.data?.url),
    [detail.data?.content_html, detail.data?.url],
  );

  // generateAi.reset 来自 mutation observer，跨渲染稳定，可以安全放进依赖
  const { reset: resetAi } = generateAi;

  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
    setReadWords(0);
    setSummaryOpen(true);
    resetAi();
  }, [itemId, resetAi]);

  useEffect(() => {
    if (!flash) return;
    const timer = window.setTimeout(() => setFlash(null), 1800);
    return () => window.clearTimeout(timer);
  }, [flash]);

  if (!itemId) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-surface">
        <EmptyState>{t.article.pick}</EmptyState>
      </div>
    );
  }

  if (detail.isPending) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-surface text-sm text-ink-3">
        {t.loading}
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-surface">
        <EmptyState>{t.error}</EmptyState>
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
      setFlash(t.article.linkCopied);
    } catch {
      setFlash(url);
    }
  };

  const exportMarkdown = () => {
    const meta = [
      `# ${item.title}`,
      '',
      `- ${t.export.source}：${item.feed_title}`,
      item.author ? `- ${t.article.author}：${item.author}` : null,
      `- ${t.export.time}：${absoluteTime(item.published_at, locale)}`,
      item.url ? `- ${t.export.original}：${item.url}` : null,
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
              {t.article.progress(readWords, wordCount)}
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
          {isEssay ? (
            <>
              <AiButton
                label={t.ai.summarize}
                icon={<Sparkles size={14} />}
                active={Boolean(summary)}
                busy={generateAi.isPending && generateAi.variables?.kind === 'summary'}
                disabled={!aiReady || generateAi.isPending}
                onClick={() => {
                  setSummaryOpen(true);
                  generateAi.mutate({ articleId: item.id, kind: 'summary' });
                }}
              />
              <AiButton
                label={t.ai.translate}
                icon={<Languages size={14} />}
                active={Boolean(translatedTitle)}
                busy={generateAi.isPending && generateAi.variables?.kind === 'title_translation'}
                disabled={!aiReady || generateAi.isPending}
                onClick={() => generateAi.mutate({ articleId: item.id, kind: 'title_translation' })}
              />
              <span className="mx-1 h-5 w-px bg-line" />
            </>
          ) : null}

          <IconButton
            label={item.is_read ? t.article.markUnread : t.article.markRead}
            active={item.is_read}
            onClick={() => setState.mutate({ id: item.id, is_read: !item.is_read })}
          >
            {item.is_read ? <CheckCircle2 size={16} /> : <Check size={16} />}
          </IconButton>
          <IconButton
            label={item.is_favorite ? t.article.unfavorite : t.article.favorite}
            active={item.is_favorite}
            onClick={() => setState.mutate({ id: item.id, is_favorite: !item.is_favorite })}
          >
            {item.is_favorite ? (
              <BookmarkCheck size={16} className="text-brand" />
            ) : (
              <Bookmark size={16} />
            )}
          </IconButton>
          <IconButton label={t.article.share} onClick={share}>
            <Share2 size={16} />
          </IconButton>
          <IconButton label={t.article.exportMarkdown} onClick={exportMarkdown}>
            <FileText size={16} />
          </IconButton>
          <IconButton label={t.article.exportPdf} onClick={() => window.print()}>
            <Download size={16} />
          </IconButton>
        </div>
      </header>

      <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
        <article className="mx-auto max-w-[660px] px-6 py-8">
          <h1 className="text-3xl font-bold leading-snug text-ink">{item.title}</h1>

          {translatedTitle ? (
            <p className="mt-2 flex items-start gap-2 text-base font-semibold text-brand-ink">
              <Languages size={15} className="mt-1 shrink-0" />
              <span>{translatedTitle.content}</span>
            </p>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-2 border-b border-line pb-5 text-xs text-ink-2">
            <SourceLogo name={item.feed_title} iconUrl={item.feed_icon_url} size={20} />
            <span className="font-semibold text-ink">{item.feed_title}</span>
            {item.author ? <span>· {t.article.author} {item.author}</span> : null}
            <span>· {absoluteTime(item.published_at, locale)}</span>
            {isEssay && wordCount > 0 ? (
              <span>· {t.article.minutes.replace('{n}', String(readingMinutes(wordCount, locale)))}</span>
            ) : null}
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-auto text-brand-ink underline underline-offset-2"
              >
                {t.article.openOriginal}
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
              src={mediaUrl(item.image_url)}
              alt={item.title}
              referrerPolicy="no-referrer"
              className="mt-6 w-full rounded-lg"
            />
          ) : null}

          {summary && summaryOpen ? (
            <section className="mt-6 rounded-xl border border-line bg-page px-4 py-3.5 print:hidden">
              <header className="flex items-center gap-2">
                <Sparkles size={14} className="text-brand-ink" />
                <span className="text-sm font-semibold text-ink">{t.ai.summaryTitle}</span>
                <span className="truncate text-2xs text-ink-3">{summary.model}</span>
                <button
                  type="button"
                  aria-label={t.ai.collapseSummary}
                  onClick={() => setSummaryOpen(false)}
                  className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-subtle hover:text-ink"
                >
                  <ChevronUp size={15} />
                </button>
              </header>
              <p className="mt-2 whitespace-pre-wrap text-[13.5px] leading-[1.8] text-ink">
                {summary.content}
              </p>
            </section>
          ) : null}

          {isEssay && !summary && summaryOpen && generateAi.isError ? (
            <p className="mt-6 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger-ink print:hidden">
              {generateAi.error instanceof Error ? generateAi.error.message : t.error}
            </p>
          ) : null}

          <div className="article-body mt-6" dangerouslySetInnerHTML={{ __html: html }} />

          <nav className="mt-10 flex items-center justify-between border-t border-line pt-5 print:hidden">
            <IconButton
              label={t.article.prev}
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
              label={t.article.next}
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

/** 顶栏的 AI 软按钮（设计稿：indigo-50 底 + indigo 文字，12/600）。 */
function AiButton({
  label,
  icon,
  active,
  busy,
  disabled,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  active: boolean;
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        active ? 'bg-soft text-on-soft' : 'text-ink-2 hover:bg-subtle hover:text-ink'
      }`}
    >
      {busy ? <Loader2 size={14} className="animate-spin" /> : icon}
      {label}
    </button>
  );
}
