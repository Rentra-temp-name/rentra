import Link from "next/link";

type AnimatedLinkButtonProps = {
  href: string;
  children: React.ReactNode;
};

export function AnimatedLinkButton({ href, children }: AnimatedLinkButtonProps) {
  return (
    <Link className="tenant-button" href={href}>
      <span>{children}</span>
    </Link>
  );
}
