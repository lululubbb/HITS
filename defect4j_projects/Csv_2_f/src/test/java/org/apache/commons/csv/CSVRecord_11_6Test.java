package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_11_6Test {

    private Constructor<CSVRecord> constructor;

    @BeforeEach
    public void setUp() throws Exception {
        constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
    }

    @Test
    @Timeout(8000)
    public void testSize_withNonEmptyValues() throws Exception {
        String[] values = new String[] { "a", "b", "c" };
        Map<String, Integer> mapping = Collections.emptyMap();
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 1L);

        int size = record.size();

        assertEquals(3, size);
    }

    @Test
    @Timeout(8000)
    public void testSize_withEmptyValues() throws Exception {
        String[] values = new String[0];
        Map<String, Integer> mapping = Collections.emptyMap();
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 1L);

        int size = record.size();

        assertEquals(0, size);
    }

    @Test
    @Timeout(8000)
    public void testSize_withNullValuesReflection() throws Exception {
        // Create instance with non-null values array
        String[] values = new String[] { "x" };
        Map<String, Integer> mapping = Collections.emptyMap();
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 1L);

        // Use reflection to set private final field 'values' to null and check behavior
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier to allow setting the field to null
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~Modifier.FINAL);

        valuesField.set(record, null);

        // Since size() returns values.length, this will throw NullPointerException
        try {
            record.size();
        } catch (NullPointerException e) {
            // Expected exception, test passes
            return;
        }
        // Fail if no exception thrown
        throw new AssertionError("Expected NullPointerException when values is null");
    }
}