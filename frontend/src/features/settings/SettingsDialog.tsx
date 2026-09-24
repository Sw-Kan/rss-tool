import * as Tabs from '@radix-ui/react-tabs';
import { Globe, Palette, Plug, Rss, Sparkles, Zap, type LucideIcon } from 'lucide-react';

import { Modal } from '../../components/Modal';
import { strings } from '../../lib/strings';
import { AiTab } from './AiTab';
import { AppearanceTab } from './AppearanceTab';
import { PlaceholderTab } from './PlaceholderTab';
import { RssTab } from './RssTab';

export const SETTINGS_TABS = [
  'appearance',
  'rss',
  'ai',
  'integrations',
  'automation',
  'proxy',
] as const;

export type SettingsTab = (typeof SETTINGS_TABS)[number];

const TAB_META: { id: SettingsTab; label: string; icon: LucideIcon }[] = [
  { id: 'appearance', label: strings.settings.tabAppearance, icon: Palette },
  { id: 'rss', label: strings.settings.tabRss, icon: Rss },
  { id: 'ai', label: strings.settings.tabAi, icon: Sparkles },
  { id: 'integrations', label: strings.settings.tabIntegrations, icon: Plug },
  { id: 'automation', label: strings.settings.tabAutomation, icon: Zap },
  { id: 'proxy', label: strings.settings.tabProxy, icon: Globe },
];

const TITLES: Record<SettingsTab, { title: string; subtitle: string }> = {
  appearance: {
    title: strings.settings.appearanceTitle,
    subtitle: strings.settings.appearanceSubtitle,
  },
  rss: { title: strings.settings.rssTitle, subtitle: strings.settings.rssSubtitle },
  ai: { title: strings.settings.tabAi, subtitle: '供应商、模型与 token 用量' },
  integrations: { title: strings.settings.tabIntegrations, subtitle: 'RSSHub / Obsidian / 飞书' },
  automation: { title: strings.settings.tabAutomation, subtitle: '当 → 如果 → 则 规则' },
  proxy: { title: strings.settings.tabProxy, subtitle: 'HTTP / HTTPS / NO_PROXY' },
};

interface SettingsDialogProps {
  open: boolean;
  activeTab: SettingsTab;
  onTabChange: (tab: SettingsTab) => void;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({
  open,
  activeTab,
  onTabChange,
  onOpenChange,
}: SettingsDialogProps) {
  const { title, subtitle } = TITLES[activeTab];

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      subtitle={subtitle}
      width={960}
      container={({ sidebar, panel }) => (
        <Tabs.Root
          value={activeTab}
          onValueChange={(value) => onTabChange(value as SettingsTab)}
          orientation="vertical"
          className="flex min-h-0 flex-1"
        >
          {sidebar}
          {panel}
        </Tabs.Root>
      )}
      sidebar={
        <>
          <div className="px-6 pt-6 pb-4">
            <p className="text-xl font-bold text-ink">{strings.settings.title}</p>
            <p className="mt-0.5 text-xs text-ink-3">{strings.settings.subtitle}</p>
          </div>
          <Tabs.List className="flex flex-col gap-1 px-4">
            {TAB_META.map(({ id, label, icon: Icon }) => (
              <Tabs.Trigger
                key={id}
                value={id}
                className="flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-ink-2 transition-colors data-[state=active]:bg-soft data-[state=active]:text-on-soft hover:bg-subtle"
              >
                <Icon size={15} />
                {label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </>
      }
    >
      <Tabs.Content value="appearance" className="outline-none">
        <AppearanceTab />
      </Tabs.Content>
      <Tabs.Content value="rss" className="outline-none">
        <RssTab />
      </Tabs.Content>
      <Tabs.Content value="ai" className="outline-none">
        <AiTab />
      </Tabs.Content>
      {(['integrations', 'automation', 'proxy'] as const).map((id) => (
        <Tabs.Content key={id} value={id} className="outline-none">
          <PlaceholderTab />
        </Tabs.Content>
      ))}
    </Modal>
  );
}
