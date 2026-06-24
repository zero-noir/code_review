import adapter from '@sveltejs/adapter-vercel';

const config = {
  kit: {
    adapter: adapter({
      runtime: 'nodejs20.x'
    })
  }
};

export default config;