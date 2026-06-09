Title: AI Gateway, Free AI API & AI Applications

URL Source: https://agnes-ai.com/doc/agnes-image-21-flash

Markdown Content:
## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580348ffcfc7f9d1a3527 "Agnes Image 2.1 Flash")Agnes Image 2.1 Flash

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5808bb602ffda297c8617 "Model Overview")Model Overview

**Agnes Image 2.1 Flash**is an upgraded image generation model by Sapiens AI, supporting both**text-to-image**and**image-to-image**workflows.

Compared with previous versions, Agnes Image 2.1 Flash provides improved performance for**high-information-density images**, making it more suitable for scenarios that require complex visual details, richer composition, and clearer semantic alignment.

Agnes Image 2.1 Flash can be used to generate images from text prompts, transform existing images, preserve original composition during editing, and return results either as image URLs or Base64 data.

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5800ba12dccc0382bf315 "Key Capabilities")Key Capabilities

Capability Description
Text-to-Image Generate high-quality images from natural language prompts
Image-to-Image Transform or refine existing images based on prompt instructions
High-Information-Density Image Optimization Improved handling of images with rich details, complex layouts, and dense visual elements
Composition Preservation Preserve the original composition when editing or transforming input images
Flexible Size Control Supports custom output sizes such as`1024x768`
URL Response Return generated image results as accessible image URLs
Base64 Response Return generated image results as Base64 data when required
URL or Data URI Input Image-to-image supports public image URLs or Data URI Base64 input

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580a6ae41f57f498bbaa9 "Applicable Scenarios")Applicable Scenarios

Agnes Image 2.1 Flash is suitable for:

Scenario Example Use Cases
Creative Design Concept art, visual exploration, poster drafts
Marketing Content Campaign images, product visuals, social media creatives
High-Density Visual Generation Detailed scenes, rich compositions, complex environments
Image Transformation Style transfer, scene re-lighting, background transformation
Content Production App assets, thumbnails, banners, storytelling visuals
Product Visualization Product photos, mockups, commercial visuals
Social Media Assets Covers, banners, thumbnails, post images

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5804b8bbbcd721f6cb9f1 "API Information")API Information

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580ae8de1e94f87d8c3da "Base URL")Base URL

`https://apihub.agnes-ai.com`
### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee58053a2ecd298131316ba "Endpoint")Endpoint

Item Description
API Endpoint`https://apihub.agnes-ai.com/v1/images/generations`
Request Method`POST`
Content-Type`application/json`
Authentication Bearer Token
Authentication Header`Authorization: Bearer YOUR_API_KEY`

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5802caf05e190a730a6b9 "Model")Model

Use the following model name for both text-to-image and image-to-image workflows:

`agnes-image-2.1-flash`

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580a685c1d249e12ee24c "Important Notes")Important Notes

*   Use`agnes-image-2.1-flash`as the model name.

*   For text-to-image generation,`model`,`prompt`, and`size`are required.

*   For image-to-image generation, provide the input image URL or Data URI Base64 in the top-level`image`array.

*   Do not put`response_format`at the top level of the request body.

*   If you need URL output, put`"response_format": "url"`inside`extra_body`.

*   If you need Base64 output for text-to-image, you can use the top-level parameter`"return_base64": true`.

*   For image-to-image Base64 output, use`"response_format": "b64_json"`inside`extra_body`.

*   You do not need to pass`tags: ["img2img"]`for image-to-image requests.

*   Do not expose temporary API keys in public documentation. Use`YOUR_API_KEY`in all public examples.

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580908f0ad8c42327edbd "Request Parameters")Request Parameters

Parameter Type Required Description
`model`string Yes Model name. Use`agnes-image-2.1-flash`
`prompt`string Yes Text instruction for image generation or image editing
`size`string Yes Output image size, such as`1024x768`
`image`string[]Required for image-to-image Input image array. Supports public image URLs or Data URI Base64
`return_base64`boolean No Used when text-to-image output should be returned as Base64
`extra_body`object No Additional parameters for advanced workflows
`extra_body.response_format`string No Output format. Common values:`url`,`b64_json`

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580cc8222c74b9c93dc2c "Call Examples")Call Examples

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580cda8eadad737d8eb40 "1. Text-to-Image Request with URL Output")1. Text-to-Image Request with URL Output

Use this request to generate an image from a text prompt and return the result as an image URL.

```
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A luminous floating city above a misty canyon at sunrise, cinematic realism",
    "size": "1024x768",
    "extra_body": {
      "response_format": "url"
    }
  }'
```

The generated image URL is returned in:

`data[0].url`

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee58081900afd2cd4d4e578 "2. Text-to-Image Request with Base64 Output")2. Text-to-Image Request with Base64 Output

Use this request when you want the generated image returned as Base64 data.

```
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
    "size": "1024x768",
    "return_base64": true
  }'
```

The generated Base64 image is returned in:

`data[0].b64_json`

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5806b81d3e0f27a312c26 "3. Image-to-Image Request with URL Input and URL Output")3. Image-to-Image Request with URL Input and URL Output

Use this request to transform an existing image while preserving the original composition.

```
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
	     "image": [
      "https://example.com/input-image.png"
    ],
      "response_format": "url"
    }
  }'
```

The generated image URL is returned in:

`data[0].url`

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee58032b9bcede3e129a3e1 "4. Image-to-Image Request with URL Input and Base64 Output")4. Image-to-Image Request with URL Input and Base64 Output

Use this request when the input image is provided as a public URL and the generated result should be returned as Base64 data.

```
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Make the object orange while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
	    "image": [
      "https://example.com/input-image.png"
    ],
      "response_format": "b64_json"
    }
  }'
```

The generated Base64 image is returned in:

`data[0].b64_json`

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580289398f8933a9491e8 "5. Image-to-Image Request with Data URI Base64 Input")5. Image-to-Image Request with Data URI Base64 Input

Image-to-image also supports Data URI Base64 input.

Data URI format:

`data:image/png;base64,BASE64_HERE`
Request example:

```
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Make the object matte black while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
	     "image": [
      "data:image/png;base64,BASE64_HERE"
    ],
      "response_format": "b64_json"
    }
  }'
```

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580d38869e2d329e12053 "Response Format")Response Format

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580f6b4a8d2cfb5b696c1 "URL Output")URL Output

When`extra_body.response_format`is set to`url`, the response format is:

```
{
  "created": 1780000000,
  "data": [
    {
      "url": "https://storage.googleapis.com/agnes-aigc/xxx.png",
      "b64_json": null,
      "revised_prompt": null
    }
  ]
}
```

Generated image URL:

`data[0].url`

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580f1958cda01ebc46f16 "Base64 Output")Base64 Output

When Base64 output is enabled, the response format is:

```
{
  "created": 1780000000,
  "data": [
    {
      "url": null,
      "b64_json": "iVBORw0KGgoAAAANSUhEUgAA...",
      "revised_prompt": null
    }
  ]
}
```

Generated Base64 image:

`data[0].b64_json`

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580ce9f96f31280f78009 "Recommended Prompt Structure")Recommended Prompt Structure

For better image generation results, use a clear prompt structure:

`[Subject] + [Scene / Environment] + [Style] + [Lighting] + [Composition] + [Quality Requirements]`
### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee58011b6f2e5a135038a5a "Example")Example

`A luminous floating city above a misty canyon at sunrise, cinematic realism, wide-angle composition, rich architectural details, soft golden light, high visual density`
For image-to-image tasks, clearly describe what should change and what should remain unchanged.

`Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition and main subject layout.`

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5807d8f9fe98db8f1a18d "Best Practices")Best Practices

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5806c8882d650e6008c50 "For Text-to-Image")For Text-to-Image

Use detailed prompts when generating complex images. Include subject, environment, style, lighting, camera angle, and desired level of detail.

Good example:

`A futuristic city marketplace filled with flying vehicles, holographic signs, dense crowds, neon lighting, cinematic realism, ultra-detailed, high-information-density composition`
Recommended elements:

*   Main subject

*   Scene or environment

*   Visual style

*   Lighting

*   Camera angle

*   Composition

*   Detail level

*   Quality requirements

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee58032b0ebd97e1aa5a0b2 "For Image-to-Image")For Image-to-Image

When editing an existing image, clearly specify both the transformation and the preservation requirements.

Good example:

`Convert the image into a fantasy winter landscape, add snow, warm window lights, and a magical atmosphere, while preserving the original building structure and camera angle.`
Recommended structure:

`[Change requirement] + [New style / scene] + [Elements to add or remove] + [Elements to preserve]`
Example:

`Change the daytime street scene into a cinematic cyberpunk night scene, add neon signs and wet road reflections, while preserving the original street layout, camera angle, and main building shapes.`

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580e38043d3649c4ee75b "For High-Information-Density Images")For High-Information-Density Images

Agnes Image 2.1 Flash is optimized for complex and detail-rich visuals. For best results, describe the visual hierarchy clearly.

Recommended elements:

*   Main subject

*   Background environment

*   Important secondary details

*   Style and lighting

*   Composition constraints

*   What should remain unchanged, if using image-to-image

Good example:

`A large fantasy harbor city built on cliffs, hundreds of small boats, layered stone bridges, glowing windows, distant mountains, cloudy sunset sky, cinematic fantasy realism, wide-angle composition, rich architectural details, high visual density`

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580598ddcc4e8f3647dd7 "Common Errors and Troubleshooting")Common Errors and Troubleshooting

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee5802a876fd09fad4a53a0 "1. response_format at the Top Level Causes an Error")1.`response_format`at the Top Level Causes an Error

Do not put`response_format`at the top level.

Incorrect:

```
{
  "model": "agnes-image-2.1-flash",
  "prompt": "A futuristic city",
  "size": "1024x768",
  "response_format": "url"
}
```

Correct:

```
{
  "model": "agnes-image-2.1-flash",
  "prompt": "A futuristic city",
  "size": "1024x768",
  "extra_body": {
    "response_format": "url"
  }
}
```

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580988dd2f41b2d57fd5d "2. Image-to-Image Does Not Require tags")2. Image-to-Image Does Not Require`tags`

Do not pass:

```
{
  "tags": ["img2img"]
}
```

For image-to-image, only provide the input image in the`image`array.

Correct:

```
{
  "model": "agnes-image-2.1-flash",
  "prompt": "Make the object blue while preserving the original composition",
  "size": "1024x768",
  "extra_body": {
    "image": [
    "https://example.com/input.png"
  ],
    "response_format": "url"
  }
}
```

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580b29146cac0db4e44de "3. Input Image URL Is Not Accessible")3. Input Image URL Is Not Accessible

If the input image URL cannot be accessed by the server, the request may fail.

Recommended solutions:

*   Use a public HTTPS image URL.

*   Make sure the image URL does not require login, cookies, or private headers.

*   Use Data URI Base64 input if the image cannot be publicly accessed.

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580e28389d3f2886bffb2 "4. Request Timeout")4. Request Timeout

Image generation may take several seconds to tens of seconds depending on the prompt complexity, image size, and server load.

Recommended client timeout:

`60s to 360s`

* * *

### [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580e697d3d8f831970be0 "5. Missing image in Image-to-Image Requests")5. Missing`image`in Image-to-Image Requests

For image-to-image generation, the`image`array is required.

Incorrect:

```
{
  "model": "agnes-image-2.1-flash",
  "prompt": "Make the image cyberpunk style",
  "size": "1024x768"
}
```

Correct:

```
{
  "model": "agnes-image-2.1-flash",
  "prompt": "Make the image cyberpunk style while preserving the original composition",
  "size": "1024x768",
  "extra_body": {
    "image": [
    "https://example.com/input.png"
  ],
    "response_format": "url"
  }
}
```

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580dc964dca04f204776c "Pricing")Pricing

Type Price
Generated Images 0

~~$0.003~~
/ image

* * *

## [](https://agnes-ai.com/doc/agnes-image-21-flash#3764a189eee580c399a0ea968ca3510c "Notes")Notes

*   Use`agnes-image-2.1-flash`as the model name.

*   Use`https://apihub.agnes-ai.com/v1/images/generations`as the API endpoint.

*   For text-to-image generation,`model`,`prompt`, and`size`are required.

*   For image-to-image generation, provide the input image URL or Data URI Base64 under the top-level`image`array.

*   Use`extra_body.response_format: "url"`when you want the generated result returned as an image URL.

*   Use`return_base64: true`for text-to-image Base64 output.

*   Use`extra_body.response_format: "b64_json"`for image-to-image Base64 output.

*   Do not put`response_format`at the top level.

*   Do not pass`tags: ["img2img"]`.

*   Do not expose temporary API keys in public documentation. Use`YOUR_API_KEY`in all public examples.
