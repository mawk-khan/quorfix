"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { useSession } from "@/lib/auth/session-provider";
import { loginSchema, type LoginFormValues } from "@/lib/validation/auth";

export default function SignInPage() {
  const router = useRouter();
  const { refetch } = useSession();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

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

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="w-full max-w-sm space-y-4"
        aria-label="Sign in"
      >
        <h1 className="text-xl font-semibold">Sign in</h1>

        <div>
          <label htmlFor="email" className="block text-sm font-medium">
            Email
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
            autoComplete="current-password"
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
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
