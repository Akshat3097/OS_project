import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function Markdown({ text }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}
                     components={{ a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" /> }}>
        {text || ""}
      </ReactMarkdown>
    </div>
  );
}
