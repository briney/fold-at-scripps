import type { JSX } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, register as registerUser } from "@/lib/api";

const registerSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  display_name: z.string().min(1, "Display name is required"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type RegisterValues = z.infer<typeof registerSchema>;

/** Public registration page: creates a pending account and confirms submission. */
export default function RegisterPage(): JSX.Element {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const mutation = useMutation({
    mutationFn: (values: RegisterValues) =>
      registerUser(values.email, values.password, values.display_name),
  });

  const apiError = mutation.error instanceof ApiError ? mutation.error.detail : undefined;

  function onSubmit(values: RegisterValues): void {
    mutation.mutate(values);
  }

  if (mutation.isSuccess) {
    return (
      <div className="flex min-h-svh items-center justify-center p-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <h1 className="font-semibold leading-none tracking-tight">Registration received</h1>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Your account is pending approval. You will be able to log in once an administrator
              approves your account.
            </p>
          </CardContent>
          <CardFooter>
            <Link to="/login" className="text-sm underline-offset-4 hover:underline">
              Back to log in
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
          <h1 className="font-semibold leading-none tracking-tight">Register</h1>
          <CardDescription>Create a fold@Scripps account.</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <CardContent className="space-y-4">
            {apiError ? (
              <p role="alert" className="text-sm text-destructive">
                {apiError}
              </p>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" {...register("email")} />
              {errors.email ? (
                <p className="text-sm text-destructive">{errors.email.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="display_name">Display name</Label>
              <Input
                id="display_name"
                type="text"
                autoComplete="name"
                {...register("display_name")}
              />
              {errors.display_name ? (
                <p className="text-sm text-destructive">{errors.display_name.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                {...register("password")}
              />
              {errors.password ? (
                <p className="text-sm text-destructive">{errors.password.message}</p>
              ) : null}
            </div>
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3">
            <Button type="submit" disabled={mutation.isPending}>
              Register
            </Button>
            <Link
              to="/login"
              className="text-sm text-muted-foreground underline-offset-4 hover:underline"
            >
              Already have an account? Log in
            </Link>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
