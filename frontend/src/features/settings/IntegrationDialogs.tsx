import { useEffect, useState } from 'react';

import { useDefaultExportSchema, useTestCustomExport, useUpdateIntegration } from '../../api/hooks';
import { Button } from '../../components/Button';
import { Field, TextArea, TextInput } from '../../components/Field';
import { Modal } from '../../components/Modal';
import { useT } from '../../lib/i18n';
import type { CustomExportConfig } from '../../types';

/** 「自定义导出」：推送接口 + JSON 模板 + 测试推送。 */
export function CustomExportDialog({
  open,
  onOpenChange,
  config,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: CustomExportConfig;
}) {
  const t = useT();
  const update = useUpdateIntegration();
  const test = useTestCustomExport();
  const defaultSchema = useDefaultExportSchema();

  const [endpoint, setEndpoint] = useState(config.endpoint);
  const [schema, setSchema] = useState(config.schema_template);

  useEffect(() => {
    if (!open) return;
    setEndpoint(config.endpoint);
    setSchema(config.schema_template || defaultSchema.data?.schema_template || '');
  }, [open, config.endpoint, config.schema_template, defaultSchema.data?.schema_template]);

  const save = () => {
    update.mutate(
      { kind: 'custom_export', custom_export: { endpoint: endpoint.trim(), schema_template: schema } },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={t.integrationDialog.customTitle}
      subtitle={t.integrationDialog.customHint}
      width={560}
      footer={
        <>
          <Button
            variant="outline"
            className="w-[132px] text-xs"
            disabled={test.isPending}
            onClick={() => test.mutate()}
          >
            {test.isPending ? t.integrationDialog.testPush : t.integrationDialog.testPush}
          </Button>
          <Button variant="outline" className="w-[136px]" onClick={() => onOpenChange(false)}>
            {t.cancel}
          </Button>
          <Button variant="solid" className="w-[136px]" onClick={save}>
            {t.save}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={t.integrationDialog.endpoint} hint={t.integrationDialog.endpointHint}>
          <TextInput
            value={endpoint}
            placeholder="https://api.example.com/rss/import"
            onChange={(event) => setEndpoint(event.target.value)}
          />
        </Field>

        <div>
          <span className="mb-1 block text-xs font-medium text-ink-2">
            {t.integrationDialog.schema}
          </span>
          <TextArea
            rows={9}
            value={schema}
            spellCheck={false}
            onChange={(event) => setSchema(event.target.value)}
          />
          <span className="mt-1 block text-xs text-ink-3">{t.integrationDialog.schemaVars}</span>
        </div>

        {test.data ? (
          <p
            className={`rounded-lg px-3 py-2 text-xs ${
              test.data.ok ? 'bg-success-soft text-success-ink' : 'bg-danger-soft text-danger-ink'
            }`}
          >
            {test.data.ok
              ? t.integrationDialog.testOk(test.data.latency_ms)
              : test.data.message}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
