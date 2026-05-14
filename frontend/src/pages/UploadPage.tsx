import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const MAX_SIZE_MB = 300;
const ACCEPTED_EXTS = ['mp4', 'mov'];

export default function UploadPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: '',
    sns: '',
    event: '',
    file: null as File | null,
    snsConsent: '',
    agree: false,
  });
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    const nextValue = type === 'checkbox' && e.target instanceof HTMLInputElement
      ? e.target.checked
      : value;
    setForm(f => ({ ...f, [name]: nextValue }));
  };

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (!file) return;
    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    if (!ACCEPTED_EXTS.includes(ext)) {
      setError('対応形式は mp4, mov, MOV のみです');
      setForm(f => ({ ...f, file: null }));
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`ファイルサイズ上限は${MAX_SIZE_MB}MBです`);
      return;
    }
    setError('');
    setForm(f => ({ ...f, file }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!form.file) {
      setError('動画ファイルを選択してください');
      return;
    }
    if (!form.agree) {
      setError('注意事項への同意が必要です');
      return;
    }

    const formData = new FormData();
    formData.append('name', form.name);
    formData.append('sns', form.sns);
    formData.append('event', form.event);
    formData.append('snsConsent', form.snsConsent);
    formData.append('agree', String(form.agree));
    formData.append('file', form.file);

    const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
    const endpoint = apiBase ? `${apiBase}/api/upload` : '/api/upload';

    try {
      setIsSubmitting(true);
      const res = await fetch(endpoint, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'アップロードに失敗しました');
      }

      const data = await res.json();
      if (!data.receiptId) {
        throw new Error('受付番号の発行に失敗しました');
      }
      navigate(`/done?rid=${encodeURIComponent(data.receiptId)}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'アップロード中にエラーが発生しました';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="upload-page" style={{ maxWidth: 480, margin: '0 auto', padding: 16 }}>
      <h2>動画アップロード</h2>
      <form onSubmit={handleSubmit}>
        <label>名前またはニックネーム<br />
          <input name="name" value={form.name} onChange={handleChange} required style={{ width: '100%' }} />
        </label>
        <br />
        <label>Instagram ID または LINE表示名<br />
          <input name="sns" value={form.sns} onChange={handleChange} required style={{ width: '100%' }} />
        </label>
        <br />
        <label>種目<br />
          <input name="event" value={form.event} onChange={handleChange} required style={{ width: '100%' }} />
        </label>
        <br />
        <label>動画ファイル（mp4, mov, MOV）<br />
          <input name="file" type="file" accept=".mp4,.mov,.MOV" ref={fileInput} onChange={handleFile} required />
        </label>
        <br />
        <label>SNS掲載可否<br />
          <select name="snsConsent" value={form.snsConsent} onChange={handleChange} required style={{ width: '100%' }}>
            <option value="">選択してください</option>
            <option value="ok">掲載可</option>
            <option value="ng">掲載不可</option>
          </select>
        </label>
        <br />
        <label>
          <input name="agree" type="checkbox" checked={form.agree} onChange={handleChange} required />
          注意事項に同意する
        </label>
        <br />
        {error && <div style={{ color: 'red', margin: '1em 0' }}>{error}</div>}
        <button
          type="submit"
          disabled={isSubmitting}
          style={{ width: '100%', padding: '1em', background: '#1976d2', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, opacity: isSubmitting ? 0.7 : 1 }}
        >
          {isSubmitting ? 'アップロード中...' : 'アップロード'}
        </button>
      </form>
    </main>
  );
}
