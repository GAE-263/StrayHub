"use client";

import React from "react";
import { Alert } from "../../components/ui/alert";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

type Props = {
  organizationName: string;
  onSwitch: () => void;
  contextMismatch?: boolean;
};

export function ActiveShelterContext({
  organizationName,
  onSwitch,
  contextMismatch = false,
}: Props) {
  return (
    <section className="active-shelter-context" aria-label="目前收容所">
      <span className="active-shelter-identity">
        目前操作收容所：{organizationName} <Badge>作用中</Badge>
      </span>
      {contextMismatch && (
        <Alert role="alert">
          目前頁面與操作中的收容所不一致，請先明確切換收容所。
        </Alert>
      )}
      <Button variant="secondary" type="button" onClick={onSwitch}>
        切換收容所
      </Button>
    </section>
  );
}
