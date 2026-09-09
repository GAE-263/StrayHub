import { redirect } from "next/navigation";
import LoginClient from "./LoginClient";
import { hasForbiddenLoginQuery } from "./login-url-policy";

type LoginPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const query = await searchParams;
  if (hasForbiddenLoginQuery(query)) {
    redirect("/login");
  }

  return <LoginClient />;
}
