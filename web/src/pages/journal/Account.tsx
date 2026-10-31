import { useParams } from "react-router-dom"

export default function JournalAccountPage() {
  const { accountId } = useParams()
  return <h1 className="text-[16px] font-semibold text-strong">Journal account {accountId}</h1>
}
