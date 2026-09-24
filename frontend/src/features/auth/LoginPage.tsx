import * as Tabs from '@radix-ui/react-tabs';
import { Lock, Mail, Rss } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useState, type FormEvent } from 'react';

import { useLogin, useRegister, useSkipLogin } from '../../api/hooks';
import { Button } from '../../components/Button';
import { Field, TextInput } from '../../components/Field';
import { strings } from '../../lib/strings';

type Mode = 'login' | 'signup';

export function LoginPage() {
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();
  const login = useLogin();
  const register = useRegister();
  const skip = useSkipLogin();

  const busy = login.isPending || register.isPending || skip.isPending;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const onSuccess = () => navigate('/reader', { replace: true });
    const onError = (cause: unknown) =>
      setError(cause instanceof Error ? cause.message : strings.error);

    if (mode === 'login') {
      login.mutate({ email, password }, { onSuccess, onError });
    } else {
      register.mutate({ username, email, password }, { onSuccess, onError });
    }
  };

  return (
    <div className="relative flex h-full items-center justify-center bg-page">
      <div className="absolute top-8 right-8 inline-flex h-9 items-center gap-2 rounded-full border border-line bg-surface px-4 text-xs text-ink-2">
        <Rss size={14} className="text-brand" />
        中文
      </div>

      <div className="w-[420px] max-w-[calc(100vw-32px)] rounded-xl bg-surface p-7 shadow-[var(--shadow-card)]">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-soft text-brand">
            <Rss size={22} />
          </span>
          <span>
            <span className="block text-2xl font-bold text-ink">{strings.appName}</span>
            <span className="block text-xs text-ink-3">{strings.appTagline}</span>
          </span>
        </div>

        <Tabs.Root value={mode} onValueChange={(value) => setMode(value as Mode)}>
          <Tabs.List className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-subtle p-1">
            <Tabs.Trigger
              value="login"
              className="h-8 rounded-md text-sm font-semibold text-ink-2 data-[state=active]:bg-surface data-[state=active]:text-ink"
            >
              {strings.auth.login}
            </Tabs.Trigger>
            <Tabs.Trigger
              value="signup"
              className="h-8 rounded-md text-sm font-semibold text-ink-2 data-[state=active]:bg-surface data-[state=active]:text-ink"
            >
              {strings.auth.signup}
            </Tabs.Trigger>
          </Tabs.List>

          <Tabs.Content value={mode} className="outline-none">
            <form onSubmit={submit} className="space-y-4">
            <p className="text-sm text-ink-2">
              {mode === 'login' ? strings.auth.loginHint : strings.auth.signupHint}
            </p>

            {mode === 'signup' ? (
              <Field label={strings.auth.username}>
                <TextInput
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                  maxLength={60}
                  autoComplete="username"
                />
              </Field>
            ) : null}

            <Field label={strings.auth.email}>
              <div className="relative">
                <Mail
                  size={15}
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3"
                />
                <TextInput
                  type="email"
                  className="pl-9"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="user@example.com"
                  required
                  autoComplete="email"
                />
              </div>
            </Field>

            <Field label={strings.auth.password}>
              <div className="relative">
                <Lock
                  size={15}
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3"
                />
                <TextInput
                  type="password"
                  className="pl-9"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••"
                  required
                  minLength={mode === 'signup' ? 8 : 1}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                />
              </div>
            </Field>

            {error ? (
              <p className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger-ink">{error}</p>
            ) : null}

              <Button type="submit" variant="solid" className="w-full" disabled={busy}>
                {mode === 'login' ? strings.auth.login : strings.auth.signup}
              </Button>
            </form>
          </Tabs.Content>
        </Tabs.Root>

        <Button
          variant="soft"
          className="mt-3 w-full"
          disabled={busy}
          onClick={() =>
            skip.mutate(undefined, {
              onSuccess: () => navigate('/reader', { replace: true }),
              onError: (cause) => setError(cause instanceof Error ? cause.message : strings.error),
            })
          }
        >
          {strings.auth.skip}
        </Button>

        <p className="mt-4 text-center text-xs text-ink-3">{strings.auth.localNote}</p>
      </div>
    </div>
  );
}
