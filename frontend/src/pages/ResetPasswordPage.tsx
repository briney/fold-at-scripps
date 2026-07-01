import type { JSX } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, redeemPasswordReset } from "@/lib/api";

const resetSchema = z.object({
  new_password: z.string().min(8, "Password must be at least 8 characters"),
});

type ResetValues = z.infer<typeof resetSchema>;

/** Public reset-password page: redeems a token from the URL to set a new password. */
export default function ResetPasswordPage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetValues>({ resolver: zodResolver(resetSchema) });

  const mutation = useMutation({
    mutationFn: (values: ResetValues) => redeemPasswordReset(token, values.new_password),
  });

  const apiError = mutation.error instanceof ApiError ? mutation.error.detail : undefined;

  function onSubmit(values: ResetValues): void {
    mutation.mutate(values);
  }

  if (mutation.isSuccess) {
    return (
      <div className="flex min-h-svh items-center justify-center p-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <h1 className="font-semibold leading-none tracking-tight">Password updated</h1>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Your password has been updated. You can now log in with your new password.
            </p>
          </CardContent>
          <CardFooter>
            <Link to="/login" className="text-sm underline-offset-4 hover:underline">
              Go to log in
            </Link>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <h1 className="font-semibold leading-none tracking-tight">Reset password</h1>
          <CardDescription>Choose a new password for your account.</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <CardContent className="space-y-4">
            {apiError ? (
              <p role="alert" className="text-sm text-destructive">
                {apiError}
              </p>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="new_password">New password</Label>
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                {...register("new_password")}
              />
              {errors.new_password ? (
                <p className="text-sm text-destructive">{errors.new_password.message}</p>
              ) : null}
            </div>
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3">
            <Button type="submit" disabled={mutation.isPending}>
              Set password
            </Button>
            <Link
              to="/login"
              className="text-sm text-muted-foreground underline-offset-4 hover:underline"
            >
              Back to log in
            </Link>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
