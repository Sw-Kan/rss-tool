import * as Tabs from '@radix-ui/react-tabs';
import { Globe, Palette, Plug, Rss, Sparkles, Zap, type LucideIcon } from 'lucide-react';

import { Modal } from '../../components/Modal';
import { useT } from '../../lib/i18n';
import { AiTab } from './AiTab';
import { AutomationTab } from './AutomationTab';
import { AppearanceTab } from './AppearanceTab';
import { IntegrationsTab } from './IntegrationsTab';
import { ProxyTab } from './ProxyTab';
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
  const t = useT();

  const tabMeta: { id: SettingsTab; label: string; icon: LucideIcon }[] = [
    { id: 'appearance', label: t.settings.tabAppearance, icon: Palette },
    { id: 'rss', label: t.settings.tabRss, icon: Rss },
    { id: 'ai', label: t.settings.tabAi, icon: Sparkles },
    { id: 'integrations', label: t.settings.tabIntegrations, icon: Plug },
    { id: 'automation', label: t.settings.tabAutomation, icon: Zap },
    { id: 'proxy', label: t.settings.tabProxy, icon: Globe },
  ];

  const titles: Record<SettingsTab, { title: string; subtitle: string }> = {
    appearance: {
      title: t.settings.appearanceTitle,
      subtitle: t.settings.appearanceSubtitle,
    },
    rss: { title: t.settings.rssTitle, subtitle: t.settings.rssSubtitle },
    ai: { title: t.settings.tabAi, subtitle: t.ai.subtitle },
    integrations: {
      title: t.settings.tabIntegrations,
      subtitle: t.settings.subtitleIntegrations,
    },
    automation: { title: t.settings.tabAutomation, subtitle: t.settings.subtitleAutomation },
    proxy: { title: t.settings.tabProxy, subtitle: t.settings.subtitleProxy },
  };

  const { title, subtitle } = titles[activeTab];

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      subtitle={subtitle}
      width={960}
      height={760}
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
            <p className="text-xl font-bold text-ink">{t.settings.title}</p>
            <p className="mt-0.5 text-xs text-ink-3">{t.settings.subtitle}</p>
          </div>
          <Tabs.List className="flex flex-col gap-1 px-4">
            {tabMeta.map(({ id, label, icon: Icon }) => (
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
      <Tabs.Content value="integrations" className="outline-none">
        <IntegrationsTab />
      </Tabs.Content>
      <Tabs.Content value="automation" className="outline-none">
        <AutomationTab />
      </Tabs.Content>
      <Tabs.Content value="proxy" className="outline-none">
        <ProxyTab />
      </Tabs.Content>
    </Modal>
  );
}
