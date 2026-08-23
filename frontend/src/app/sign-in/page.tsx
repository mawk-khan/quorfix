"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { demoLogin, login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import type { CommunityRole } from "@/lib/api/types";
import { useSession } from "@/lib/auth/session-provider";
import { DEMO_ROLES } from "@/lib/demo";
import { errorProps } from "@/lib/forms/error-props";
import { usePageTitle } from "@/lib/use-page-title";
import { loginSchema, type LoginFormValues } from "@/lib/validation/auth";

export default function SignInPage() {
  const router = useRouter();
  const { session, refetch } = useSession();
  const [formError, setFormError] = useState<string | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  // Which role's Quick Access button is mid-request, if any — drives both
  // the per-button loading label and the "prevent double submission" guard
  // below. Never derived from anything persisted (e.g. localStorage): it's
  // plain in-memory UI state for one in-flight request.
  const [pendingRole, setPendingRole] = useState<CommunityRole | null>(null);
  usePageTitle("Sign in");

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  // Authoritative, backend-owned flag (settings.QUORFIX_DEMO_MODE, surfaced
  // via SessionSerializer — see apps/organizations/views.py). Never a
  // NEXT_PUBLIC_* build-time variable: a value the client could assert on
  // its own must never be what gates showing (let alone using) demo login.
  const demoModeEnabled = session?.demo_mode === true;
  const demoLoginPending = pendingRole !== null;

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
      refetch();
      router.push("/");
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setFormError("Too many attempts. Try again in a moment.");
      } else {
        setFormError("Invalid email or password.");
      }
    }
  };

  // Calls the password-less demo-login endpoint directly — this never
  // touches, fills, or submits the email/password fields above, so no
  // demo credential is ever placed in the DOM, in frontend source, or in a
  // NEXT_PUBLIC_* variable. See apps/accounts/views.py's DemoLoginView.
  const handleDemoLogin = async (role: CommunityRole) => {
    if (demoLoginPending || isSubmitting) return;
    setDemoError(null);
    setPendingRole(role);
    try {
      await demoLogin(role);
      refetch();
      router.push("/");
    } catch {
      setDemoError("Couldn't open the demo right now. Please try again.");
      setPendingRole(null);
    }
  };

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="flex min-h-screen items-center justify-center bg-page p-4 sm:p-8"
    >
      <div className="w-full max-w-sm space-y-4">
        {demoModeEnabled && (
          <>
            <Card>
              <CardContent className="space-y-4">
                <div className="space-y-1 text-center">
                  <h1 className="text-lg font-semibold text-text-primary">Explore Quorfix</h1>
                  <p className="text-sm text-text-secondary">
                    Choose a role to enter the live demo. No account required.
                  </p>
                </div>

                {demoError && (
                  <p role="alert" className="text-center text-sm text-danger">
                    {demoError}
                  </p>
                )}

                <div
                  role="group"
                  aria-label="Explore Quorfix by role"
                  className="grid grid-cols-2 gap-2"
                >
                  {DEMO_ROLES.map((role) => {
                    const isPending = pendingRole === role.value;
                    return (
                      <Button
                        key={role.value}
                        type="button"
                        variant="secondary"
                        loading={isPending}
                        disabled={demoLoginPending || isSubmitting}
                        onClick={() => handleDemoLogin(role.value)}
                      >
                        {isPending ? `Opening ${role.label} demo…` : role.label}
                      </Button>
                    );
                  })}
                </div>

                <p className="text-center text-xs text-text-secondary">
                  Demo data is shared between visitors and may be reset periodically.
                </p>
              </CardContent>
            </Card>

            <div className="flex items-center gap-3 text-xs font-medium text-text-secondary">
              <span className="h-px flex-1 bg-border" aria-hidden="true" />
              or
              <span className="h-px flex-1 bg-border" aria-hidden="true" />
            </div>
          </>
        )}

        <Card>
          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" aria-label="Sign in">
              <h2 className="text-base font-semibold text-text-primary">
                {demoModeEnabled ? "Sign in with email" : "Sign in"}
              </h2>

              <FormField htmlFor="email" label="Email" error={errors.email}>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  disabled={demoLoginPending}
                  {...errorProps("email", errors.email)}
                  {...register("email")}
                />
              </FormField>

              <FormField htmlFor="password" label="Password" error={errors.password}>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  disabled={demoLoginPending}
                  {...errorProps("password", errors.password)}
                  {...register("password")}
                />
              </FormField>

              {formError && (
                <p role="alert" className="text-sm text-danger">
                  {formError}
                </p>
              )}

              <Button
                type="submit"
                className="w-full"
                loading={isSubmitting}
                disabled={isSubmitting || demoLoginPending}
              >
                {isSubmitting ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
