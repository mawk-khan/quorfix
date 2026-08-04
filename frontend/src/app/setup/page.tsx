"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "@/lib/api/client";
import { getSetupStatus, submitSetup } from "@/lib/api/setup";
import { useSession } from "@/lib/auth/session-provider";
import { setupSchema, type SetupFormValues } from "@/lib/validation/setup";

export default function SetupPage() {
  const router = useRouter();
  const { refetch } = useSession();
  const [checking, setChecking] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SetupFormValues>({ resolver: zodResolver(setupSchema) });

  useEffect(() => {
    getSetupStatus()
      .then((status) => {
        if (status.is_configured) {
          router.replace("/sign-in");
        } else {
          setChecking(false);
        }
      })
      .catch(() => setChecking(false));
  }, [router]);

  const onSubmit = async (values: SetupFormValues) => {
    setFormError(null);
    try {
      await submitSetup(values);
      refetch();
      router.push("/");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setFormError("This instance is already configured.");
      } else {
        setFormError("Something went wrong. Try again.");
      }
    }
  };

  if (checking) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p>Checking instance status…</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="w-full max-w-sm space-y-4"
        aria-label="Set up Bug Fixer"
      >
        <h1 className="text-xl font-semibold">Set up Bug Fixer</h1>
        <p className="text-sm text-gray-500">
          Create the first administrator account and organization.
        </p>

        <div>
          <label htmlFor="organization_name" className="block text-sm font-medium">
            Organization name
          </label>
          <input
            id="organization_name"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("organization_name")}
          />
          {errors.organization_name && (
            <p role="alert" className="mt-1 text-sm text-red-700">
              {errors.organization_name.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="email" className="block text-sm font-medium">
            Your email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("email")}
          />
          {errors.email && (
            <p role="alert" className="mt-1 text-sm text-red-700">
              {errors.email.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("password")}
          />
          {errors.password && (
            <p role="alert" className="mt-1 text-sm text-red-700">
              {errors.password.message}
            </p>
          )}
        </div>

        {formError && (
          <p role="alert" className="text-sm text-red-700">
            {formError}
          </p>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded bg-black px-3 py-2 text-white disabled:opacity-50"
        >
          {isSubmitting ? "Setting up…" : "Create administrator account"}
        </button>
      </form>
    </main>
  );
}
