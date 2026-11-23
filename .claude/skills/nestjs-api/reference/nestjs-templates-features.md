# NestJS Feature Templates — CRUD Module Pattern

Complete feature module templates for NestJS 11.x with controller, service, repository, and DTOs.

## Feature Module Template

### Product Feature Module (src/features/products/products.module.ts)

```typescript
import { Module } from '@nestjs/common';
import { ProductsController } from './controllers/products.controller';
import { ProductsService } from './services/products.service';
import { ProductsRepository } from './repositories/products.repository';

@Module({
  controllers: [ProductsController],
  providers: [ProductsService, ProductsRepository],
  exports: [ProductsService],
})
export class ProductsModule {}
```

### Product Controller (src/features/products/controllers/products.controller.ts)

```typescript
import {
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Body,
  Param,
  Query,
  HttpCode,
  HttpStatus,
  UseGuards,
  Logger,
} from '@nestjs/common';
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiBearerAuth,
  ApiQuery,
  ApiParam,
} from '@nestjs/swagger';

import { ProductsService } from '../services/products.service';
import { CreateProductDto } from '../dto/create-product.dto';
import { UpdateProductDto } from '../dto/update-product.dto';
import { ProductResponseDto } from '../dto/product-response.dto';
import { JwtAuthGuard } from '../../../auth/guards/jwt-auth.guard';

@ApiTags('products')
@Controller({ path: 'products', version: '1' })
@UseGuards(JwtAuthGuard)
@ApiBearerAuth()
export class ProductsController {
  private readonly logger = new Logger(ProductsController.name);

  constructor(private readonly productsService: ProductsService) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({ summary: 'Create a new product' })
  @ApiResponse({
    status: HttpStatus.CREATED,
    description: 'Product created successfully',
    type: ProductResponseDto,
  })
  @ApiResponse({
    status: HttpStatus.BAD_REQUEST,
    description: 'Invalid input data',
  })
  async create(@Body() dto: CreateProductDto): Promise<ProductResponseDto> {
    this.logger.log(`Creating product: ${dto.name}`);
    return this.productsService.create(dto);
  }

  @Get()
  @ApiOperation({ summary: 'Get all products' })
  @ApiQuery({ name: 'page', required: false, type: Number, example: 1 })
  @ApiQuery({ name: 'limit', required: false, type: Number, example: 10 })
  @ApiResponse({
    status: HttpStatus.OK,
    description: 'Products retrieved successfully',
    type: [ProductResponseDto],
  })
  async findAll(
    @Query('page') page = 1,
    @Query('limit') limit = 10,
  ): Promise<ProductResponseDto[]> {
    this.logger.log(`Fetching products - page: ${page}, limit: ${limit}`);
    return this.productsService.findAll({ page, limit });
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get product by ID' })
  @ApiParam({ name: 'id', type: String, description: 'Product ID' })
  @ApiResponse({
    status: HttpStatus.OK,
    description: 'Product retrieved successfully',
    type: ProductResponseDto,
  })
  @ApiResponse({
    status: HttpStatus.NOT_FOUND,
    description: 'Product not found',
  })
  async findOne(@Param('id') id: string): Promise<ProductResponseDto> {
    this.logger.log(`Fetching product: ${id}`);
    return this.productsService.findById(id);
  }

  @Patch(':id')
  @ApiOperation({ summary: 'Update product' })
  @ApiParam({ name: 'id', type: String, description: 'Product ID' })
  @ApiResponse({
    status: HttpStatus.OK,
    description: 'Product updated successfully',
    type: ProductResponseDto,
  })
  @ApiResponse({
    status: HttpStatus.NOT_FOUND,
    description: 'Product not found',
  })
  async update(
    @Param('id') id: string,
    @Body() dto: UpdateProductDto,
  ): Promise<ProductResponseDto> {
    this.logger.log(`Updating product: ${id}`);
    return this.productsService.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Delete product' })
  @ApiParam({ name: 'id', type: String, description: 'Product ID' })
  @ApiResponse({
    status: HttpStatus.NO_CONTENT,
    description: 'Product deleted successfully',
  })
  @ApiResponse({
    status: HttpStatus.NOT_FOUND,
    description: 'Product not found',
  })
  async delete(@Param('id') id: string): Promise<void> {
    this.logger.log(`Deleting product: ${id}`);
    await this.productsService.delete(id);
  }
}
```

### Product Service (src/features/products/services/products.service.ts)

```typescript
import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { ProductsRepository } from '../repositories/products.repository';
import type { Product } from '../../../generated/prisma/client';
import { CreateProductDto } from '../dto/create-product.dto';
import { UpdateProductDto } from '../dto/update-product.dto';
import { ProductResponseDto } from '../dto/product-response.dto';

@Injectable()
export class ProductsService {
  private readonly logger = new Logger(ProductsService.name);

  constructor(private readonly repository: ProductsRepository) {}

  async create(dto: CreateProductDto): Promise<ProductResponseDto> {
    try {
      const product = await this.repository.create({
        name: dto.name,
        description: dto.description,
        price: dto.price,
        stock: dto.stock ?? 0,
        isActive: dto.isActive ?? true,
      });

      return this.toResponseDto(product);
    } catch (error) {
      this.logger.error('Failed to create product', error);
      throw error;
    }
  }

  async findAll(options: {
    page: number;
    limit: number;
  }): Promise<ProductResponseDto[]> {
    const { page, limit } = options;
    const skip = (page - 1) * limit;

    const products = await this.repository.findMany({
      skip,
      take: limit,
      where: { deletedAt: null },
      orderBy: { createdAt: 'desc' },
    });

    return products.map((p) => this.toResponseDto(p));
  }

  async findById(id: string): Promise<ProductResponseDto> {
    const product = await this.repository.findById(id);

    if (!product || product.deletedAt) {
      throw new NotFoundException(`Product with ID ${id} not found`);
    }

    return this.toResponseDto(product);
  }

  async update(id: string, dto: UpdateProductDto): Promise<ProductResponseDto> {
    const existing = await this.repository.findById(id);

    if (!existing || existing.deletedAt) {
      throw new NotFoundException(`Product with ID ${id} not found`);
    }

    const updated = await this.repository.update(id, {
      ...dto,
      version: existing.version + 1, // Optimistic locking
    });

    return this.toResponseDto(updated);
  }

  async delete(id: string): Promise<void> {
    const product = await this.repository.findById(id);

    if (!product || product.deletedAt) {
      throw new NotFoundException(`Product with ID ${id} not found`);
    }

    // Soft delete
    await this.repository.update(id, {
      deletedAt: new Date(),
    });

    this.logger.log(`Product ${id} soft-deleted`);
  }

  private toResponseDto(product: Product): ProductResponseDto { // Product from the generated Prisma client
    return {
      id: product.id,
      name: product.name,
      description: product.description,
      price: product.price,
      stock: product.stock,
      isActive: product.isActive,
      createdAt: product.createdAt,
      updatedAt: product.updatedAt,
    };
  }
}
```

### Create Product DTO (src/features/products/dto/create-product.dto.ts)

```typescript
import { ApiProperty } from '@nestjs/swagger';
import {
  IsString,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsBoolean,
  Min,
  MaxLength,
} from 'class-validator';

export class CreateProductDto {
  @ApiProperty({ example: 'Laptop Pro', description: 'Product name' })
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  name: string;

  @ApiProperty({
    example: 'High-performance laptop for professionals',
    description: 'Product description',
    required: false,
  })
  @IsString()
  @IsOptional()
  @MaxLength(1000)
  description?: string;

  @ApiProperty({ example: 1299.99, description: 'Product price' })
  @IsNumber()
  @Min(0)
  price: number;

  @ApiProperty({ example: 50, description: 'Stock quantity', required: false })
  @IsNumber()
  @IsOptional()
  @Min(0)
  stock?: number;

  @ApiProperty({ example: true, description: 'Product active status', required: false })
  @IsBoolean()
  @IsOptional()
  isActive?: boolean;
}
```

### Update Product DTO (src/features/products/dto/update-product.dto.ts)

```typescript
import { PartialType } from '@nestjs/swagger';
import { CreateProductDto } from './create-product.dto';

export class UpdateProductDto extends PartialType(CreateProductDto) {}
```

### Product Response DTO (src/features/products/dto/product-response.dto.ts)

```typescript
import { ApiProperty } from '@nestjs/swagger';

export class ProductResponseDto {
  @ApiProperty({ example: 'cm3a1b2c3d4e5f6g7h8i9' })
  id: string;

  @ApiProperty({ example: 'Laptop Pro' })
  name: string;

  @ApiProperty({ example: 'High-performance laptop for professionals' })
  description?: string;

  @ApiProperty({ example: 1299.99 })
  price: number;

  @ApiProperty({ example: 50 })
  stock: number;

  @ApiProperty({ example: true })
  isActive: boolean;

  @ApiProperty({ example: '2026-02-02T10:30:00.000Z' })
  createdAt: Date;

  @ApiProperty({ example: '2026-02-02T10:30:00.000Z' })
  updatedAt: Date;
}
```

### Product Repository (src/features/products/repositories/products.repository.ts)

```typescript
import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../../../core/database/services/prisma.service';
import { Prisma, Product } from '@prisma/client';

@Injectable()
export class ProductsRepository {
  private readonly logger = new Logger(ProductsRepository.name);

  constructor(private readonly prisma: PrismaService) {}

  async create(data: Prisma.ProductCreateInput): Promise<Product> {
    return this.prisma.product.create({ data });
  }

  async findById(id: string): Promise<Product | null> {
    return this.prisma.product.findUnique({ where: { id } });
  }

  async findMany(args: Prisma.ProductFindManyArgs): Promise<Product[]> {
    return this.prisma.product.findMany(args);
  }

  async update(id: string, data: Prisma.ProductUpdateInput): Promise<Product> {
    return this.prisma.product.update({
      where: { id },
      data,
    });
  }

  async delete(id: string): Promise<Product> {
    return this.prisma.product.delete({ where: { id } });
  }

  async count(where?: Prisma.ProductWhereInput): Promise<number> {
    return this.prisma.product.count({ where });
  }
}
```
