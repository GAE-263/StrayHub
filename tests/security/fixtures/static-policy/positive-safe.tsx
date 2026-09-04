export function SafeLogin() {
  const page = 2;
  const photo = `/v1/public/animals/fixture/photo?token=${capability}`;
  return <form action="/login" method="post"><input type="password" name="password" /><span>{page}{photo}</span></form>;
}
